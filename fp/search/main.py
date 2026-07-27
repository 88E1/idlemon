import logging
import random
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import constants
from data.pkmn_sets import SmogonSets
from fp.battle import Battle, Pokemon
from config import FoulPlayConfig

from poke_engine import (
    State as PokeEngineState,
    monte_carlo_tree_search,
    MctsResult,
)

from fp.search.poke_engine_helpers import battle_to_poke_engine_state

logger = logging.getLogger(__name__)

NUM_RESERVES = 2


def team_preview_shuffle(battle):
    """
    poke-engine needs pkmn in the active slots all the time, even during team preview
    """
    battle.user.slot_a.active = battle.user.reserve.pop(0)
    battle.user.slot_b.active = battle.user.reserve.pop(0)
    battle.opponent.slot_a.active = battle.opponent.reserve.pop(0)
    battle.opponent.slot_b.active = battle.opponent.reserve.pop(0)


def sample_pkmn_to_remove(pkmn_list: list[Pokemon]):
    # sample a non-restricted pokemon to remove if available, otherwise sample any pokemon
    pkmn_to_sample_from = [
        p
        for p in pkmn_list
        if p.name not in constants.RESTRICTED_POKEMON and not p.revealed
    ] or [p for p in pkmn_list if not p.revealed]
    return random.choice(pkmn_to_sample_from)


def sample_unrevealed_pkmn(battle: Battle, num_teams: int) -> list[(Battle, float)]:
    battle = deepcopy(battle)
    num_reserves = NUM_RESERVES

    battles = []
    for i in range(num_teams):
        battle_copy = deepcopy(battle)
        while len(battle_copy.opponent.reserve) > num_reserves:
            pkmn = sample_pkmn_to_remove(battle_copy.opponent.reserve)
            battle_copy.opponent.reserve.remove(pkmn)

        assert len(battle_copy.opponent.reserve) == 2
        populate_spreads(battle_copy, i)
        battle_copy.opponent.slot_a.lock_moves()
        battle_copy.opponent.slot_b.lock_moves()
        battles.append((battle_copy, 1 / num_teams))

    return battles


def get_battles_for_team_preview(battle: Battle) -> list[Battle]:
    # for all 6 pkmn in the opponent's reserve, create a battle of 4 pkmn
    # get all 15 combinations of 4 pkmn from the 6
    from itertools import combinations

    battles = []
    i = 0
    for reserve_comb in combinations(battle.opponent.reserve, 4):
        battle_copy = deepcopy(battle)
        battle_copy.opponent.reserve = deepcopy(list(reserve_comb))
        team_preview_shuffle(battle_copy)
        populate_spreads(battle_copy, i)
        battle_copy.opponent.slot_a.lock_moves()
        battle_copy.opponent.slot_b.lock_moves()
        battles.append((battle_copy, 1 / 15))
        i += 1
    return battles


def populate_spreads(battle: Battle, index: int):
    logger.info("Battle {}".format(index))
    for pkmn in [
        battle.opponent.slot_a.active,
        battle.opponent.slot_b.active,
    ] + battle.opponent.reserve:
        if pkmn.hp <= 0:
            continue

        pkmn_spread = SmogonSets.get_random_spread(pkmn)
        if pkmn_spread is None:
            logger.warning("\tNo spread found for {}".format(pkmn.name))
        else:
            pkmn.set_spread(pkmn_spread.nature, pkmn_spread.evs)
            logger.info(
                "\tPredicted Set: {} {} for {}".format(
                    pkmn_spread.nature.ljust(7), str(pkmn.evs).ljust(25), pkmn.name
                )
            )


def select_move_from_mcts_results(mcts_results: list[(MctsResult, float, int)]) -> tuple[str, str]:
    final_policy = {}
    for mcts_result, sample_chance, index in mcts_results:
        this_policy = max(mcts_result.side_one, key=lambda x: x.visits)
        logger.info(
            "Policy {}: {} visited {}% avg_score={} sample_chance_multiplier={}".format(
                index,
                this_policy.move_choice,
                round(100 * this_policy.visits / mcts_result.total_visits, 2),
                round(this_policy.total_score / this_policy.visits, 3),
                round(sample_chance, 3),
            )
        )
        for s1_option in mcts_result.side_one:
            final_policy[s1_option.move_choice] = final_policy.get(
                s1_option.move_choice, 0
            ) + (sample_chance * (s1_option.visits / mcts_result.total_visits))

    final_policy = sorted(final_policy.items(), key=lambda x: x[1], reverse=True)

    logger.info("Top 5 moves from MCTS results:")
    for i, policy in enumerate(final_policy[:5]):
        logger.info(f"\t{round(policy[1] * 100, 3)}%: {policy[0]}")

    # Consider all moves that are close to the best move
    highest_percentage = final_policy[0][1]
    final_policy = [i for i in final_policy if i[1] >= highest_percentage * 0.75]
    logger.info("Considered Choices:")
    for i, policy in enumerate(final_policy):
        logger.info(f"\t{round(policy[1] * 100, 3)}%: {policy[0]}")

    choice = random.choices(final_policy, weights=[p[1] for p in final_policy])[0]
    return choice[0]


def get_result_from_mcts(state: str, search_time_ms: int, index: int) -> MctsResult:
    logger.debug("Calling with {} state: {}".format(index, state))
    poke_engine_state = PokeEngineState.from_string(state)
    res = monte_carlo_tree_search(poke_engine_state, search_time_ms)
    logger.info("Iterations {}: {}".format(index, res.total_visits))
    return res


def find_best_move(battle):
    if battle.team_preview:
        battles = get_battles_for_team_preview(battle)
        parallelism = FoulPlayConfig.parallelism
        search_time_per_battle = FoulPlayConfig.search_time_ms // 2
    else:
        num_teams = 2
        parallelism = FoulPlayConfig.parallelism
        search_time_per_battle = FoulPlayConfig.search_time_ms
        battles = sample_unrevealed_pkmn(battle, num_teams)

    num_battles = len(battles)

    logger.info("Searching for a move using MCTS...")
    logger.info(
        "Sampling {} battles at {}ms each".format(num_battles, search_time_per_battle)
    )

    with ThreadPoolExecutor(max_workers=parallelism) as executor:
        futures = []
        for index, (b, chance) in enumerate(battles):
            fut = executor.submit(
                get_result_from_mcts,
                battle_to_poke_engine_state(b).to_string(),
                search_time_per_battle,
                index,
            )
            futures.append((fut, chance, index))

    mcts_results = [(fut.result(), chance, index) for (fut, chance, index) in futures]

    choice = select_move_from_mcts_results(mcts_results)
    logger.info("Choice: {}".format(choice))

    return choice
