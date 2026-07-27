import json
import asyncio
import logging

import constants
from config import DecisionMode, FoulPlayConfig, SaveReplay
from data.pkmn_sets import SmogonSets
from fp.battle import LastUsedMove, Pokemon, Battle
from fp.search.helpers import format_decision
from fp.battle_modifier import async_update_battle
from fp.helpers import normalize_name
from fp.heuristic import pick_moves, pick_team_preview_digits
from fp.agent_chooser import pick_moves_agent, pick_team_preview_digits_agent
from fp.llm_chooser import pick_moves_llm, pick_team_preview_digits_llm

from fp.websocket_client import PSWebsocketClient

logger = logging.getLogger(__name__)


async def _select_moves(battle):
    if FoulPlayConfig.decision_mode == DecisionMode.llm:
        return await asyncio.to_thread(pick_moves_llm, battle)
    if FoulPlayConfig.decision_mode == DecisionMode.agent:
        return await asyncio.to_thread(pick_moves_agent, battle)
    return pick_moves(battle)


async def _select_team_preview_digits(battle):
    if FoulPlayConfig.decision_mode == DecisionMode.llm:
        return await asyncio.to_thread(pick_team_preview_digits_llm, battle)
    if FoulPlayConfig.decision_mode == DecisionMode.agent:
        return await asyncio.to_thread(pick_team_preview_digits_agent, battle)
    return pick_team_preview_digits(battle)


def battle_is_finished(battle_tag, msg):
    return (
        msg.startswith(">{}".format(battle_tag))
        and (constants.WIN_STRING in msg or constants.TIE_STRING in msg)
        and constants.CHAT_STRING not in msg
    )


def bo3_is_finished(bo3_tag, msg):
    return (
        msg.startswith(">{}".format(bo3_tag))
        and (constants.WIN_STRING in msg or constants.TIE_STRING in msg)
        and constants.CHAT_STRING not in msg
    )


def extract_battle_factory_tier_from_msg(msg):
    start = msg.find("Battle Factory Tier: ") + len("Battle Factory Tier: ")
    end = msg.find("</b>", start)
    tier_name = msg[start:end]

    return normalize_name(tier_name)


async def async_pick_move(battle):
    if not battle.team_preview:
        battle.user.update_from_request_json(battle.request_json)

    choice_a, choice_b = await _select_moves(battle)
    battle.user.slot_a.last_selected_move = LastUsedMove(
        battle.user.slot_a.active.name,
        choice_a.split(",")[0],
        battle.turn,
    )
    battle.user.slot_b.last_selected_move = LastUsedMove(
        battle.user.slot_b.active.name,
        choice_b.split(",")[0],
        battle.turn,
    )
    decision_a = format_decision(battle, battle.user.slot_a, choice_a)
    decision_b = format_decision(battle, battle.user.slot_b, choice_b)
    logger.debug("moves: %s, %s", decision_a, decision_b)
    return decision_a, decision_b


async def handle_team_preview(battle, ps_websocket_client):
    digits = await _select_team_preview_digits(battle)

    choice_digit_a = int(digits[0])
    choice_digit_b = int(digits[1])
    choice_digit_reserve_1 = int(digits[2])
    choice_digit_reserve_2 = int(digits[3])
    pkmn_name_a = battle.user.find_pkmn_by_index(choice_digit_a).name
    pkmn_name_b = battle.user.find_pkmn_by_index(choice_digit_b).name
    res1_name = battle.user.find_pkmn_by_index(choice_digit_reserve_1).name
    res2_name = battle.user.find_pkmn_by_index(choice_digit_reserve_2).name

    battle.user.slot_a.last_selected_move = LastUsedMove(
        "teampreview", "switch {}".format(pkmn_name_a), battle.turn
    )
    battle.user.slot_b.last_selected_move = LastUsedMove(
        "teampreview", "switch {}".format(pkmn_name_b), battle.turn
    )
    message = [
        "/team {}{}{}{}|{}".format(
            choice_digit_a,
            choice_digit_b,
            choice_digit_reserve_1,
            choice_digit_reserve_2,
            battle.rqid,
        )
    ]
    chosen_pkmn = [res1_name, res2_name, pkmn_name_a, pkmn_name_b]
    logger.info(
        "Chosen pokemon (leads first): {}, {}, {}, {}".format(
            pkmn_name_a, pkmn_name_b, res1_name, res2_name
        )
    )
    for pkmn in battle.user.reserve:
        if pkmn.name not in chosen_pkmn:
            logger.info("Marking {} as fainted (not chosen)".format(pkmn.name))
            pkmn.hp = 0
            pkmn.name = "none"

    await ps_websocket_client.send_message(battle.battle_tag, message)


async def get_battle_tag_and_opponent(ps_websocket_client: PSWebsocketClient):
    while True:
        msg = await ps_websocket_client.receive_message()
        split_msg = msg.split("|")
        first_msg = split_msg[0]
        # Surface matchmaking / validation feedback; otherwise the bot sits
        # silently forever if the team is rejected or search never starts.
        if len(split_msg) > 1 and split_msg[1] in (
            "popup",
            "updatesearch",
            "nametaken",
            "error",
        ):
            logger.info("Matchmaking message: %s", msg[:500])
        if "battle" in first_msg:
            battle_tag = first_msg.replace(">", "").strip()
            user_name = FoulPlayConfig.username
            opponent_name = (
                split_msg[4].replace(user_name, "").replace("vs.", "").strip()
            )
            return battle_tag, opponent_name


async def start_battle_common(
    ps_websocket_client: PSWebsocketClient, pokemon_battle_type
):
    battle_tag, opponent_name = await get_battle_tag_and_opponent(ps_websocket_client)
    if FoulPlayConfig.log_to_file:
        FoulPlayConfig.file_log_handler.do_rollover(
            "{}_{}.log".format(battle_tag, opponent_name)
        )

    battle = Battle(battle_tag)
    battle.opponent.account_name = opponent_name
    battle.generation = pokemon_battle_type[:4]

    # wait until the opponent's identifier is received. This will be `p1` or `p2`.
    #
    # e.g.
    # '>battle-gen9randombattle-44733
    # |player|p1|OpponentName|2|'
    while True:
        msg = await ps_websocket_client.receive_message()
        if "|player|" in msg and battle.opponent.account_name in msg:
            battle.opponent.name = msg.split("|")[2]
            battle.user.name = constants.ID_LOOKUP[battle.opponent.name]
            break

    return battle, msg


async def get_first_request_json(
    ps_websocket_client: PSWebsocketClient, battle: Battle
):
    while True:
        msg = await ps_websocket_client.receive_message()
        msg_split = msg.split("|")
        if msg_split[1].strip() == "request" and msg_split[2].strip():
            user_json = json.loads(msg_split[2].strip("'"))
            battle.request_json = user_json
            battle.user.initialize_first_turn_user_from_json(user_json)
            battle.rqid = user_json[constants.RQID]
            return


def _parse_showteam(msg, opponent_name):
    prefix = "|showteam|{}|".format(opponent_name)
    for line in msg.split("\n"):
        if line.startswith(prefix):
            return line[len(prefix) :]
    return None


def _parse_team_preview_species(msg, opponent_name):
    # `|poke|<player>|<details>|<item>` lines reveal opponent species at team preview
    species = []
    for line in msg.split("\n"):
        parts = line.split("|")
        if len(parts) >= 4 and parts[1] == "poke" and parts[2] == opponent_name:
            species.append(parts[3])
    return species


def _try_parse_request(msg, battle):
    for line in msg.split("\n"):
        msg_split = line.split("|")
        if (
            len(msg_split) > 2
            and msg_split[1].strip() == "request"
            and msg_split[2].strip()
        ):
            user_json = json.loads(msg_split[2].strip("'"))
            battle.request_json = user_json
            battle.user.initialize_first_turn_user_from_json(user_json)
            battle.rqid = user_json[constants.RQID]
            return True
    return False


async def start_standard_battle(
    ps_websocket_client: PSWebsocketClient,
    pokemon_battle_type,
    first_battle,
):
    battle, msg = await start_battle_common(ps_websocket_client, pokemon_battle_type)
    battle.battle_type = constants.STANDARD_BATTLE

    while constants.START_TEAM_PREVIEW not in msg:
        msg = await ps_websocket_client.receive_message()

    # VGC/Champions formats use Open Team Sheets: the opponent's full `|showteam|`
    # packed team is only revealed once OTS is accepted. Accept it so we get the
    # opponent's sheet when possible; if it never arrives (e.g. the opponent
    # declines) we fall back to the species-only team-preview info.
    if "acceptopenteamsheets" in msg:
        await ps_websocket_client.send_message(
            battle.battle_tag, ["/acceptopenteamsheets"]
        )

    opponent_showteam = _parse_showteam(msg, battle.opponent.name)
    opponent_species = _parse_team_preview_species(msg, battle.opponent.name)

    # Read until the team-preview request arrives, capturing the opponent's
    # showteam line along the way if it is revealed.
    logger.debug("waiting for request_json (opp=%s)", battle.opponent.name)
    while battle.request_json is None:
        msg = await ps_websocket_client.receive_message()
        if opponent_showteam is None:
            opponent_showteam = _parse_showteam(msg, battle.opponent.name)
        if not opponent_species:
            opponent_species = _parse_team_preview_species(msg, battle.opponent.name)
        _try_parse_request(msg, battle)
    logger.debug(
        "got request_json rqid=%s showteam=%s species=%s",
        battle.rqid,
        bool(opponent_showteam),
        opponent_species,
    )

    if opponent_showteam:
        battle.opponent.from_packed_string(opponent_showteam)
    else:
        battle.opponent.from_team_preview_species(opponent_species)
        logger.info(
            "No open team sheet available; using species-only opponent info: {}".format(
                [p.name for p in battle.opponent.reserve]
            )
        )

    logger.debug("start_standard_battle: during_team_preview")
    battle.during_team_preview()

    if first_battle:
        SmogonSets.initialize(pokemon_battle_type, battle)

    SmogonSets.load_speed_ranges(battle)
    battle.user.reserve.insert(0, battle.user.slot_a.active)
    battle.user.reserve.insert(0, battle.user.slot_b.active)
    battle.user.slot_a.active = None
    battle.user.slot_b.active = None
    await handle_team_preview(battle, ps_websocket_client)
    return battle


async def start_battle(ps_websocket_client, pokemon_battle_type, first_battle):
    battle = await start_standard_battle(
        ps_websocket_client, pokemon_battle_type, first_battle
    )

    await ps_websocket_client.send_message(battle.battle_tag, ["/timer on"])

    return battle


async def pokemon_battle(
    ps_websocket_client, pokemon_battle_type, best_of_3_room_name, first_battle
):
    battle = await start_battle(ps_websocket_client, pokemon_battle_type, first_battle)
    while True:
        msg = await ps_websocket_client.receive_message()
        if battle_is_finished(battle.battle_tag, msg):
            if constants.WIN_STRING in msg:
                winner = msg.split(constants.WIN_STRING)[-1].split("\n")[0].strip()
            else:
                winner = None
            logger.info("Winner: {}".format(winner))
            if FoulPlayConfig.save_replay == SaveReplay.always or (
                FoulPlayConfig.save_replay == SaveReplay.on_loss
                and winner != FoulPlayConfig.username
            ):
                await ps_websocket_client.save_replay(battle.battle_tag)
            await ps_websocket_client.leave_battle(battle.battle_tag)
            SmogonSets.save_speed_ranges(battle)
            return winner, False
        elif bo3_is_finished(best_of_3_room_name, msg):
            if constants.WIN_STRING in msg:
                winner = msg.split(constants.WIN_STRING)[-1].split("\n")[0].strip()
            else:
                winner = None
            logger.info("Bo3 Winner: {}".format(winner))
            if FoulPlayConfig.save_replay == SaveReplay.always or (
                FoulPlayConfig.save_replay == SaveReplay.on_loss
                and winner != FoulPlayConfig.username
            ):
                await ps_websocket_client.save_replay(battle.battle_tag)
            await ps_websocket_client.leave_battle(battle.battle_tag)
            return winner, True
        else:
            action_required = await async_update_battle(battle, msg)
            if action_required and not battle.wait:
                decision_a, decision_b = await async_pick_move(battle)
                cmd = "/choose {}, {}".format(decision_a, decision_b)
                logger.info(f"sending {cmd}")
                await ps_websocket_client.send_message(
                    battle.battle_tag, [cmd, str(battle.rqid)]
                )
