import logging

import constants
from data import pokedex
from fp.battle import Battle, Pokemon, Battler, Slot, LastUsedMove

from poke_engine import (
    Weather as PokeEngineWeather,
    Terrain as PokeEngineTerrain,
    State as PokeEngineState,
    Side as PokeEngineSide,
    SideSlot as PokeEngineSideSlot,
    SideConditions as PokeEngineSideConditions,
    VolatileStatusDurations as PokeEngineVolatileStatusDurations,
    Pokemon as PokeEnginePokemon,
    Move as PokeEngineMove,
    calculate_damage,
    PokemonIndex,
)

logger = logging.getLogger(__name__)


WEATHERS = {
    None: PokeEngineWeather.NONE,
    "none": PokeEngineWeather.NONE,
    constants.SUN: PokeEngineWeather.SUN,
    constants.RAIN: PokeEngineWeather.RAIN,
    constants.SAND: PokeEngineWeather.SAND,
    constants.HAIL: PokeEngineWeather.HAIL,
    constants.SNOW: PokeEngineWeather.SNOW,
    constants.DESOLATE_LAND: PokeEngineWeather.HARSH_SUN,
    constants.HEAVY_RAIN: PokeEngineWeather.HEAVY_RAIN,
}


TERRAINS = {
    None: PokeEngineTerrain.NONE,
    "none": PokeEngineTerrain.NONE,
    constants.ELECTRIC_TERRAIN: PokeEngineTerrain.ELECTRIC,
    constants.GRASSY_TERRAIN: PokeEngineTerrain.GRASSY,
    constants.MISTY_TERRAIN: PokeEngineTerrain.MISTY,
    constants.PSYCHIC_TERRAIN: PokeEngineTerrain.PSYCHIC,
}


def status_to_string(status):
    if status == constants.SLEEP:
        return "Sleep"
    elif status == constants.BURN:
        return "Burn"
    elif status == constants.FROZEN:
        return "Freeze"
    elif status == constants.PARALYZED:
        return "Paralyze"
    elif status == constants.POISON:
        return "Poison"
    elif status == constants.TOXIC:
        return "Toxic"
    elif status is None:
        return "None"
    raise ValueError(f"Unknown status: {status}")


def pokemon_to_poke_engine_pkmn(pkmn: Pokemon):
    """
    id,level,type0,type1,hp,maxhp,ability,item,atk,def,spa,spd,spe,atkb,defb,spab,spdb,speb,accb,evab,status,subhp,restturns
    nature,volatiles,m0,m1,m2,m3
    """
    # the pkmn is not part of the battle, use the default empty pokemon
    if pkmn.name == "none" and pkmn.hp == 0:
        return PokeEnginePokemon(id="none", hp=0)

    # Gen 3/4 don't remove items if knocked off
    # but the item is not active, so lets remove it
    if pkmn.knocked_off or pkmn.item == "" or pkmn.item is None:
        pkmn.item = "None"

    base_types = pokedex[str(pkmn.name)][constants.TYPES]
    if len(base_types) == 1:
        base_types = (base_types[0], "typeless")
    if len(pkmn.types) == 1:
        pkmn.types = (pkmn.types[0], "typeless")
    num_moves = len(pkmn.moves)
    if num_moves > 4:
        logger.warning(
            "More than 4 moves on pokemon: {} moves: {}".format(
                pkmn.name, [m.name for m in pkmn.moves]
            )
        )
        logger.warning("Truncating moves to first 4")
        pkmn.moves = pkmn.moves[:4]

    pkmn_moves = [
        PokeEngineMove(id=str(m.name), disabled=m.disabled, pp=m.current_pp)
        for m in pkmn.moves
    ]
    while num_moves < 4:
        pkmn_moves.append(PokeEngineMove(id="none", disabled=True, pp=0))
        num_moves += 1

    base_ability = ""
    if pkmn.original_ability:
        base_ability = str(pkmn.original_ability)

    return PokeEnginePokemon(
        id=str(pkmn.name),
        level=pkmn.level,
        types=tuple(pkmn.types),
        base_types=tuple(base_types),
        hp=int(pkmn.hp),
        maxhp=int(pkmn.max_hp),
        ability=str(pkmn.ability),
        base_ability=base_ability,
        item=str(pkmn.item),
        nature=pkmn.nature,
        evs=tuple(pkmn.evs),
        attack=pkmn.stats[constants.ATTACK],
        defense=pkmn.stats[constants.DEFENSE],
        special_attack=pkmn.stats[constants.SPECIAL_ATTACK],
        special_defense=pkmn.stats[constants.SPECIAL_DEFENSE],
        speed=pkmn.stats[constants.SPEED],
        status=status_to_string(pkmn.status),
        rest_turns=pkmn.rest_turns,
        sleep_turns=pkmn.sleep_turns,
        weight_kg=float(pokedex[pkmn.name][constants.WEIGHT]),
        moves=pkmn_moves,
        tera_type=pkmn.tera_type or "typeless",
        terastallized=pkmn.terastallized,
        times_attacked=pkmn.times_attacked,
        stellar_boosted_types=pkmn.stellar_boosted_types,
    )


def slot_to_poke_engine_slot(
    side: Battler,
    slot: Slot,
    active_index: PokemonIndex,
    force_switch=False,
    stayed_in_on_switchout_move=False,
) -> PokeEngineSideSlot:
    last_used_move = "move:none"
    if slot.last_used_move.move.startswith("switch "):
        last_used_move = "switch:0"
    elif slot.last_used_move.move:
        pkmn_moves = [m.name for m in slot.active.moves]
        for i, move in enumerate(pkmn_moves):
            if move == slot.last_used_move.move:
                last_used_move = "move:{}".format(i)
                break
        else:
            last_used_move = "move:0"

    # substitute health can't be known with certainty but the client can keep track of if the substitute was hit
    # to approximate: the substitute health is 1/10 of the pokemon's max_hp if it was hit, 1/4 if it wasn't
    substitute_health = 0
    if constants.SUBSTITUTE in slot.active.volatile_statuses:
        if slot.active.substitute_hit:
            substitute_health = int(slot.active.max_hp / 10)
        else:
            substitute_health = int(slot.active.max_hp / 4)

    future_sight_index = 0
    if slot.future_sight[0] > 0:
        if slot.active.name == slot.future_sight[1]:
            future_sight_index = 0
        else:
            index = 1
            for pkmn in side.reserve:
                if pkmn.name == slot.future_sight[1]:
                    future_sight_index = index
                    break
                index += 1
            else:
                raise ValueError(
                    "Couldnt find future sight source: {} not in {} + {}".format(
                        slot.future_sight[1],
                        slot.active.name,
                        [p.name for p in side.reserve],
                    )
                )

    return PokeEngineSideSlot(
        active_index=active_index,
        baton_passing=slot.baton_passing,
        shed_tailing=slot.shed_tailing,
        wish=(int(slot.wish[0]), int(slot.wish[1])),
        future_sight=(slot.future_sight[0], str(future_sight_index)),
        force_switch=force_switch,
        force_trapped=slot.trapped,
        slow_uturn_move=stayed_in_on_switchout_move,
        volatile_statuses=set(slot.active.volatile_statuses),
        volatile_status_durations=PokeEngineVolatileStatusDurations(
            confusion=slot.active.volatile_status_durations[constants.CONFUSION],
            lockedmove=slot.active.volatile_status_durations[constants.LOCKED_MOVE],
            protect=slot.active.volatile_status_durations[constants.PROTECT],
            encore=slot.active.volatile_status_durations["encore"],
            slowstart=slot.active.volatile_status_durations[constants.SLOW_START],
            taunt=slot.active.volatile_status_durations[constants.TAUNT],
            yawn=slot.active.volatile_status_durations[constants.YAWN],
        ),
        substitute_health=substitute_health,
        attack_boost=slot.active.boosts[constants.ATTACK],
        defense_boost=slot.active.boosts[constants.DEFENSE],
        special_attack_boost=slot.active.boosts[constants.SPECIAL_ATTACK],
        special_defense_boost=slot.active.boosts[constants.SPECIAL_DEFENSE],
        speed_boost=slot.active.boosts[constants.SPEED],
        accuracy_boost=0,
        evasion_boost=0,
        last_used_move=last_used_move,
        switch_out_move_second_saved_move="NONE",  # always none because we can't know this
    )


def battler_to_poke_engine_side(
    battler: Battler,
    force_switch=(False, False),
    slot_a_stayed_in_on_pivot=False,
    slot_b_stayed_in_on_pivot=False,
):
    return PokeEngineSide(
        slot_a=slot_to_poke_engine_slot(
            battler,
            battler.slot_a,
            active_index=PokemonIndex.P0,
            force_switch=force_switch[0],
            stayed_in_on_switchout_move=slot_a_stayed_in_on_pivot,
        ),
        slot_b=slot_to_poke_engine_slot(
            battler,
            battler.slot_b,
            active_index=PokemonIndex.P1,
            force_switch=force_switch[1],
            stayed_in_on_switchout_move=slot_b_stayed_in_on_pivot,
        ),
        pokemon=[
            pokemon_to_poke_engine_pkmn(battler.slot_a.active),
            pokemon_to_poke_engine_pkmn(battler.slot_b.active),
        ]
        + [pokemon_to_poke_engine_pkmn(p) for p in battler.reserve],
        side_conditions=PokeEngineSideConditions(
            aurora_veil=battler.side_conditions[constants.AURORA_VEIL],
            crafty_shield=battler.side_conditions["craftyshield"],
            healing_wish=battler.side_conditions[constants.HEALING_WISH],
            light_screen=battler.side_conditions[constants.LIGHT_SCREEN],
            lucky_chant=battler.side_conditions["luckychant"],
            lunar_dance=battler.side_conditions["lunardance"],
            mat_block=battler.side_conditions["matblock"],
            mist=battler.side_conditions["mist"],
            protect=battler.side_conditions[constants.PROTECT],
            quick_guard=battler.side_conditions["quickguard"],
            reflect=battler.side_conditions[constants.REFLECT],
            safeguard=battler.side_conditions[constants.SAFEGUARD],
            spikes=battler.side_conditions[constants.SPIKES],
            stealth_rock=battler.side_conditions[constants.STEALTH_ROCK],
            sticky_web=battler.side_conditions[constants.STICKY_WEB],
            tailwind=battler.side_conditions[constants.TAILWIND],
            toxic_count=battler.side_conditions[constants.TOXIC_COUNT],
            toxic_spikes=battler.side_conditions[constants.TOXIC_SPIKES],
            wide_guard=battler.side_conditions["wideguard"],
        ),
    )


def replace_hidden_power_last_used_move(battler: Battler):
    for mv in battler.active.moves:
        if mv.name.startswith(constants.HIDDEN_POWER):
            battler.last_used_move = LastUsedMove(
                pokemon_name=battler.last_used_move.pokemon_name,
                move=mv.name,
                turn=battler.last_used_move.turn,
            )
            break
    else:
        logger.warning("Could not replace hiddenpower")
        battler.last_used_move = LastUsedMove(
            pokemon_name=battler.last_used_move.pokemon_name,
            move="switch {}".format(battler.active.name),
            turn=battler.last_used_move.turn,
        )


def replace_return_last_used_move(slot: Slot):
    for mv in slot.active.moves:
        if mv.name.startswith("return"):
            slot.last_used_move = LastUsedMove(
                pokemon_name=slot.last_used_move.pokemon_name,
                move=mv.name,
                turn=slot.last_used_move.turn,
            )
            break
    else:
        logger.warning("Could not replace return")
        slot.last_used_move = LastUsedMove(
            pokemon_name=slot.last_used_move.pokemon_name,
            move="switch {}".format(slot.active.name),
            turn=slot.last_used_move.turn,
        )


def battle_to_poke_engine_state(battle: Battle):
    # Boolean that represents if we have used a switch-out move first (i.e. fast uturn)
    # this is toggled to True if we did, and signifies to the engine that the opponent has
    # selected a move and that should be accounted for in the search
    opponent_a_stayed_in_on_pivot = False
    opponent_b_stayed_in_on_pivot = False
    bot_a_lum = battle.user.slot_a.last_used_move
    bot_b_lum = battle.user.slot_b.last_used_move
    opp_a_lum = battle.opponent.slot_a.last_used_move
    opp_b_lum = battle.opponent.slot_b.last_used_move
    if (
        bot_a_lum.move in constants.SWITCH_OUT_MOVES
        and opp_a_lum.turn != bot_a_lum.turn
    ):
        opponent_a_stayed_in_on_pivot = True
    if (
        bot_a_lum.move in constants.SWITCH_OUT_MOVES
        and opp_b_lum.turn != bot_a_lum.turn
    ):
        opponent_b_stayed_in_on_pivot = True
    if (
        bot_b_lum.move in constants.SWITCH_OUT_MOVES
        and opp_a_lum.turn != bot_a_lum.turn
    ):
        opponent_a_stayed_in_on_pivot = True
    if (
        bot_b_lum.move in constants.SWITCH_OUT_MOVES
        and opp_b_lum.turn != bot_a_lum.turn
    ):
        opponent_b_stayed_in_on_pivot = True

    if battle.user.slot_a.last_used_move.move == "return":
        replace_return_last_used_move(battle.user.slot_a)
    if battle.user.slot_b.last_used_move.move == "return":
        replace_return_last_used_move(battle.user.slot_b)

    if battle.opponent.slot_a.last_used_move.move == "return":
        replace_return_last_used_move(battle.opponent.slot_a)
    if battle.opponent.slot_b.last_used_move.move == "return":
        replace_return_last_used_move(battle.opponent.slot_b)

    side_one = battler_to_poke_engine_side(
        battle.user, force_switch=battle.force_switch
    )
    side_two = battler_to_poke_engine_side(
        battle.opponent,
        slot_a_stayed_in_on_pivot=opponent_a_stayed_in_on_pivot,
        slot_b_stayed_in_on_pivot=opponent_b_stayed_in_on_pivot,
    )

    return PokeEngineState(
        side_one=side_one,
        side_two=side_two,
        weather=WEATHERS[battle.weather],
        weather_turns_remaining=battle.weather_turns_remaining,
        terrain=TERRAINS[battle.field],
        terrain_turns_remaining=battle.field_turns_remaining,
        trick_room=battle.trick_room,
        trick_room_turns_remaining=battle.trick_room_turns_remaining,
        team_preview=battle.team_preview,
    )


def poke_engine_get_damage_rolls(
    battle: Battle,
    attacker_side_str: str,
    attacker_slot_str: str,
    target_side_str: str,
    target_slot_str: str,
    side_one_move: str,
    side_two_move: str,
):
    if side_one_move.startswith("switch"):
        side_one_move = "switch"
    if side_two_move.startswith("switch"):
        side_two_move = "switch"

    state = battle_to_poke_engine_state(battle)

    logger.debug(
        "Calling calculate damage with state: {}, attacker_side: {}, attacker_slot: {}, target_side: {}, target_slot: {}, s1_move: {}, s2_move: {}".format(
            state.to_string(),
            attacker_side_str,
            attacker_slot_str,
            target_side_str,
            target_slot_str,
            side_one_move,
            side_two_move,
        )
    )

    rolls = calculate_damage(
        state,
        attacker_side_str,
        attacker_slot_str,
        target_side_str,
        target_slot_str,
        side_one_move,
        side_two_move,
    )

    logger.debug(
        "Got Rolls rolls: {}".format(
            rolls,
        )
    )

    return rolls
