import re
import json
from copy import deepcopy
import logging

import constants
from data import all_move_json
from data import pokedex
from data.pkmn_sets import (
    SmogonSets,
)
from fp.battle import Pokemon, Battle, Slot
from fp.battle import LastUsedMove
from fp.battle import DamageDealt
from fp.battle import StatRange
from fp.search.poke_engine_helpers import poke_engine_get_damage_rolls
from fp.helpers import normalize_name
from fp.helpers import get_pokemon_info_from_condition
from fp.helpers import calculate_stats
from fp.battle import boost_multiplier_lookup


logger = logging.getLogger(__name__)

MOVE_END_STRINGS = {"move", "switch", "upkeep", ""}

SIDE_CONDITION_DEFAULT_DURATION = {
    constants.REFLECT: 5,
    constants.LIGHT_SCREEN: 5,
    constants.AURORA_VEIL: 5,
    constants.SAFEGUARD: 5,
    constants.MIST: 5,
    constants.TAILWIND: 4,
}


def crit_rate_for_generation(generation):
    if generation == "gen1":
        return 205 / 105
    elif generation in [
        "gen2",
        "gen3",
        "gen4",
        "gen5",
    ]:
        return 2.0
    else:
        return 1.5


def can_have_priority_modified(battle, pokemon, move_name):
    return (
        "prankster"
        in [
            normalize_name(a)
            for a in pokedex[pokemon.name][constants.ABILITIES].values()
        ]
        or (move_name == "grassyglide" and battle.field == constants.GRASSY_TERRAIN)
        or (
            move_name in all_move_json
            and all_move_json[move_name][constants.CATEGORY] == constants.STATUS
            and "myceliummight"
            in [
                normalize_name(a)
                for a in pokedex[pokemon.name][constants.ABILITIES].values()
            ]
        )
    )


def can_have_speed_modified(pokemon):
    return pokemon.item is None and pokemon.ability == "unburden"


def remove_volatile(pkmn, volatile):
    pkmn.volatile_statuses = [vs for vs in pkmn.volatile_statuses if vs != volatile]


def unlikely_to_have_choice_item(move_name):
    try:
        move_dict = all_move_json[move_name]
    except KeyError:
        return False

    if (
        constants.BOOSTS in move_dict
        and move_dict[constants.CATEGORY] == constants.STATUS
    ):
        return True
    elif move_name in ["substitute", "roost", "recover"]:
        return True

    return False


def is_opponent(battle, split_msg):
    return not split_msg[2].startswith(battle.user.name)


def is_slot_a(split_msg):
    return split_msg[2].startswith("p1a") or split_msg[2].startswith("p2a")


def get_side_slot_active(battle, split_msg):
    # Given a split message, return the side and slot of the active pokemon
    if is_opponent(battle, split_msg):
        side = battle.opponent
        other_side = battle.user
    else:
        side = battle.user
        other_side = battle.opponent

    if is_slot_a(split_msg):
        slot = side.slot_a
    else:
        slot = side.slot_b

    return side, other_side, slot, slot.active


def get_pkmn_from_split_msg(battle, split_msg):
    if is_opponent(battle, split_msg):
        if is_slot_a(split_msg):
            return battle.opponent.slot_a.active
        else:
            return battle.opponent.slot_b.active
    else:
        if is_slot_a(split_msg):
            return battle.user.slot_a.active
        else:
            return battle.user.slot_b.active


def get_move_information(m):
    # Given a |move| line from the PS protocol, extract the user of the move and the move object
    try:
        split_move_line = m.split("|")
        return split_move_line[2], all_move_json[normalize_name(split_move_line[3])]
    except KeyError:
        logger.warning(
            "Unknown move {} - using standard 0 priority move".format(
                normalize_name(m.split("|")[3])
            )
        )
        return m.split("|")[2], {constants.ID: "unknown", constants.PRIORITY: 0}


def request(battle, split_msg):
    if len(split_msg) >= 2:
        battle_json = json.loads(split_msg[2].strip("'"))
        logger.debug("Received battle JSON from server: {}".format(battle_json))
        battle.rqid = battle_json[constants.RQID]

        if battle_json.get(constants.FORCE_SWITCH):
            battle.force_switch = (
                battle_json[constants.FORCE_SWITCH][0],
                battle_json[constants.FORCE_SWITCH][1],
            )
        else:
            battle.force_switch = (False, False)

        if battle_json.get(constants.WAIT):
            battle.wait = True
        else:
            battle.wait = False

        battle.request_json = battle_json


def inactive(battle, split_msg):
    regex_string = r"(\d+) sec this turn"
    if split_msg[2].startswith(constants.TIME_LEFT):
        capture = re.search(regex_string, split_msg[2])
        try:
            time_left = int(capture.group(1))
            battle.time_remaining = time_left
            logger.debug("Time left: {}".format(time_left))
        except ValueError:
            logger.warning("{} is not a valid int".format(capture.group(1)))
        except AttributeError:
            logger.warning(
                "'{}' does not match the regex '{}'".format(split_msg[2], regex_string)
            )


def inactiveoff(battle, _):
    battle.time_remaining = None


def switch(battle, split_msg):
    switch_or_drag(battle, split_msg, switch_or_drag="switch")


def drag(battle, split_msg):
    switch_or_drag(battle, split_msg, switch_or_drag="drag")


def switch_or_drag(battle, split_msg, switch_or_drag="switch"):
    if is_opponent(battle, split_msg):
        side_name = "opponent"
        side = battle.opponent
        logger.info("Opponent has switched - clearing the last used move")
    else:
        side_name = "user"
        side = battle.user
        side.side_conditions[constants.TOXIC_COUNT] = 0

    if is_slot_a(split_msg):
        slot = side.slot_a
    else:
        slot = side.slot_b

    baton_passed_boosts = None
    switch_keep_volatiles = []
    if slot.active is not None:
        # set the pkmn's types back to their original value if the types were changed
        # if the pkmn is terastallized, this does not happen
        if constants.TYPECHANGE in slot.active.volatile_statuses:
            original_types = pokedex[slot.active.name][constants.TYPES]
            logger.info(
                "{} had it's type changed - changing its types back to {}".format(
                    slot.active.name, original_types
                )
            )
            slot.active.types = original_types

        # if the target was transformed, reset its transformed attributes
        if constants.TRANSFORM in slot.active.volatile_statuses:
            logger.info(
                "{} was transformed. Resetting its transformed attributes".format(
                    slot.active.name
                )
            )
            slot.active.stats = calculate_stats(
                slot.active.base_stats, slot.active.level
            )
            slot.active.ability = slot.active.original_ability
            slot.active.moves = []
            slot.active.types = pokedex[slot.active.name][constants.TYPES]

        if (
            slot.active.original_ability is not None
            and slot.active.ability != slot.active.original_ability
        ):
            logger.info(
                "{}'s ability was modified to {} - setting it back to {} on switch-out".format(
                    slot.active.name, slot.active.ability, slot.active.original_ability
                )
            )
            slot.active.ability = slot.active.original_ability
            slot.active.original_ability = None

        if split_msg[-1] == "[from] Baton Pass":
            slot.baton_passing = False
            logger.info(
                "Baton passing, preserving boosts: {}".format(dict(slot.active.boosts))
            )
            baton_passed_boosts = deepcopy(slot.active.boosts)

            if constants.SUBSTITUTE in slot.active.volatile_statuses:
                logger.info("Baton passing, preserving substitute")
                switch_keep_volatiles.append(constants.SUBSTITUTE)
            if constants.LEECH_SEED in slot.active.volatile_statuses:
                logger.info("Baton passing, preserving leechseed")
                switch_keep_volatiles.append(constants.LEECH_SEED)
        elif split_msg[-1] == "[from] Shed Tail":
            slot.shed_tailing = False

            if constants.SUBSTITUTE in slot.active.volatile_statuses:
                logger.info("Shed tailing, preserving substitute")
                switch_keep_volatiles.append(constants.SUBSTITUTE)

        # gen5 rest turns are reset upon switching
        if battle.generation == "gen5" and slot.active.status == constants.SLEEP:
            if slot.active.rest_turns != 0:
                logger.info(
                    "{} switched while asleep and with non-zero rest turns, resetting rest turns to 3".format(
                        slot.active.name
                    )
                )
                slot.active.rest_turns = 3
            else:
                logger.info(
                    "{} switched while asleep, resetting sleep turns to 0".format(
                        slot.active.name
                    )
                )
                slot.active.sleep_turns = 0

        # gen3 rest turns are decremented by the number of consecutive sleep talks
        if battle.generation == "gen3" and slot.active.status == constants.SLEEP:
            if slot.active.rest_turns != 0:
                slot.active.rest_turns += slot.active.gen_3_consecutive_sleep_talks
                logger.info(
                    "gen3 {} switched with {} consecutive sleep talks. Incrementing rest turns by {}".format(
                        slot.active.name,
                        slot.active.gen_3_consecutive_sleep_talks,
                        slot.active.gen_3_consecutive_sleep_talks,
                    )
                )
            elif slot.active.sleep_turns != 0:
                logger.info(
                    "gen3 {} switched with {} consecutive sleep talks. Decrementing sleep turns by {}".format(
                        slot.active.name,
                        slot.active.gen_3_consecutive_sleep_talks,
                        slot.active.gen_3_consecutive_sleep_talks,
                    )
                )
                slot.active.sleep_turns -= slot.active.gen_3_consecutive_sleep_talks

        slot.active.gen_3_consecutive_sleep_talks = 0

        slot.active.moves_used_since_switch_in.clear()

        # reset the boost of the pokemon being replaced
        slot.active.boosts.clear()

        # reset the volatile statuses of the pokemon being replaced
        slot.active.volatile_statuses.clear()
        slot.active.volatile_status_durations.clear()

        # reset toxic count for this side
        side.side_conditions[constants.TOXIC_COUNT] = 0

        # if the pkmn is alive and has regenerator, give it back 1/3 of it's maxhp
        if (
            slot.active.hp > 0
            and not slot.active.fainted
            and slot.active.ability == "regenerator"
        ):
            health_healed = int(slot.active.max_hp / 3)
            slot.active.hp = min(slot.active.hp + health_healed, slot.active.max_hp)
            logger.info(
                "{} switched out with regenerator. Healing it to {}/{}".format(
                    slot.active.name, slot.active.hp, slot.active.max_hp
                )
            )

        if slot.active.name in ["cramorantgulping", "cramorantgorging"]:
            logger.info(
                "Resetting {} to 'cramorant' on switch out".format(slot.active.name)
            )
            slot.active.name = "cramorant"

    # check if the pokemon exists in the reserves
    # if it does not, then the newly-created pokemon is used (for formats without team preview)
    nickname = split_msg[2]
    temp_pkmn = Pokemon.from_switch_string(split_msg[3], nickname=nickname)
    pkmn = side.find_pokemon_in_reserves(temp_pkmn.name)

    if pkmn is None:
        pkmn = Pokemon.from_switch_string(split_msg[3], nickname=nickname)

        # some pokemon do not reveal their forme during team preview. Arceus, Silvally, Genesect, etc.
        # if this is the case, they would have been given a flag during team preview, and we can pull them out here
        unknown_forme_pkmn = side.find_reserve_pkmn_by_unknown_forme(temp_pkmn.name)
        if unknown_forme_pkmn:
            side.reserve.remove(unknown_forme_pkmn)
    else:
        pkmn.nickname = temp_pkmn.nickname

        # Zoroark edge-case nonsense
        # if this pokemon turns out to be zoroark it may have permanent conditions change that need to be un-done after
        # finding out it is zoroark e.g. the HP value of this pokemon on switch-in is preserved so we can reset it if it
        # turns out to be zoroark
        pkmn.hp_at_switch_in = pkmn.hp
        pkmn.status_at_switch_in = pkmn.status

        side.reserve.remove(pkmn)

    pkmn.revealed = True
    split_hp_msg = split_msg[4].split("/")
    if is_opponent(battle, split_msg):
        new_hp_percentage = float(split_hp_msg[0]) / 100
        if (
            pkmn.hp != new_hp_percentage * pkmn.max_hp
            and "regenerator"
            in [
                normalize_name(a)
                for a in pokedex[pkmn.name][constants.ABILITIES].values()
            ]
            and pkmn.ability is None
        ):
            logger.info(
                "{} switched out with {}% HP but now has {}% HP, setting its ability to regenerator".format(
                    pkmn.name,
                    pkmn.hp / pkmn.max_hp * 100,
                    new_hp_percentage * 100,
                )
            )
            pkmn.ability = "regenerator"
        pkmn.hp = pkmn.max_hp * new_hp_percentage
    else:
        pkmn.hp = float(split_hp_msg[0])
        pkmn.max_hp = float(split_hp_msg[1].split()[0])

    slot.last_used_move = LastUsedMove(
        pokemon_name=None, move="switch {}".format(pkmn.name), turn=battle.turn
    )

    # pkmn != active is a special edge-case for Zoroark
    if slot.active is not None and pkmn != slot.active:
        side.reserve.append(slot.active)

    slot.active = pkmn

    # zacian-crowned is technically still zacian before switching in for the first time
    # this is handled by set-prediction for the opponent, but for the bot's pkmn we
    # need to re-apply the stats that the P.S. server sends us because prior to the first
    # switch-in the stats would be for zacian, not zacian-crowned
    if side_name == "user" and pkmn.name in ["zaciancrowned", "zamazentacrowned"]:
        slot.re_initialize_active_pokemon_from_request_json(battle.request_json)

    if baton_passed_boosts is not None:
        logger.info(
            "Applying baton passed boosts to {}: {}".format(
                slot.active.name, dict(baton_passed_boosts)
            )
        )
        slot.active.boosts = baton_passed_boosts
    for volatile in switch_keep_volatiles:
        logger.info("Keeping volatile on switch: {}".format(volatile))
        slot.active.volatile_statuses.append(volatile)


def sethp(battle, split_msg):
    # |-sethp|p2a: Jellicent|317/403|[from] move: Pain Split|[silent]
    if is_opponent(battle, split_msg):
        pkmn = get_pkmn_from_split_msg(battle, split_msg)
        new_hp_percentage = float(split_msg[3].split("/")[0]) / 100
        pkmn.hp = int(pkmn.max_hp * new_hp_percentage)
    else:
        pkmn = get_pkmn_from_split_msg(battle, split_msg)
        pkmn.hp = int(split_msg[3].split("/")[0])
        pkmn.max_hp = int(split_msg[3].split("/")[1].split()[0])


def heal_or_damage(battle, split_msg):
    if is_opponent(battle, split_msg):
        side, other_side, slot, pkmn = get_side_slot_active(battle, split_msg)
        if len(split_msg) == 5 and split_msg[4] == "[from] move: Revival Blessing":
            nickname = Pokemon.extract_nickname_from_pokemonshowdown_string(
                split_msg[2]
            )
            pkmn = side.find_reserve_pokemon_by_nickname(nickname)

        # opponent hp is given as a percentage
        if constants.FNT in split_msg[3]:
            pkmn.hp = 0
        else:
            new_hp_percentage = float(split_msg[3].split("/")[0]) / 100
            pkmn.hp = pkmn.max_hp * new_hp_percentage

    else:
        side, other_side, slot, pkmn = get_side_slot_active(battle, split_msg)
        if len(split_msg) == 5 and split_msg[4] == "[from] move: Revival Blessing":
            nickname = Pokemon.extract_nickname_from_pokemonshowdown_string(
                split_msg[2]
            )
            pkmn = side.find_reserve_pokemon_by_nickname(nickname)
        if constants.FNT in split_msg[3]:
            pkmn.hp = 0
        else:
            pkmn.hp = float(split_msg[3].split("/")[0])
            pkmn.max_hp = float(split_msg[3].split("/")[1].split()[0])

    # increase the amount of turns toxic has been active
    if (
        len(split_msg) == 5
        and constants.TOXIC in split_msg[3]
        and "[from] psn" in split_msg[4]
    ):
        side.side_conditions[constants.TOXIC_COUNT] += 1

    # needs verification: does a split_msg length of 4 _only_ happen when taking damage from a move?
    if split_msg[1] == "-damage" and len(split_msg) == 4:
        pkmn.times_attacked += 1
        logger.info(
            "{} took direct damage, incremented times_attacked to {}".format(
                pkmn.name, pkmn.times_attacked
            )
        )

    # commented because vgc will have revealed items
    # if (
    #     len(split_msg) == 6
    #     and split_msg[4].startswith("[from] item:")
    #     and other_side.name in split_msg[5]
    # ):
    #     item = normalize_name(split_msg[4].split("item:")[-1])
    #     logger.info("Setting {}'s item to: {}".format(other_side.active.name, item))
    #     other_side.active.item = item

    if (
        len(split_msg) >= 5
        and split_msg[-1].startswith("[from]")
        and split_msg[-1].endswith("Healing Wish")
    ):
        logger.info(
            "{} was healed from healing wish, setting side condition to 0".format(
                pkmn.name
            )
        )
        side.side_conditions[constants.HEALING_WISH] = 0

    # commented because vgc will have revealed items
    # set the ability for the other side (the side not taking damage, '-damage' only)
    # if (
    #     len(split_msg) == 6
    #     and split_msg[4].startswith("[from] ability:")
    #     and other_side.name in split_msg[5]
    #     and split_msg[1] == "-damage"
    # ):
    #     ability = normalize_name(split_msg[4].split("ability:")[-1])
    #     logger.info(
    #         "Setting {}'s ability to: {}".format(other_side.active.name, ability)
    #     )
    #     other_side.active.ability = ability

    # commented because vgc will have revealed items
    # set the ability of the side (the side being healed, '-heal' only)
    # if (
    #     len(split_msg) == 6
    #     and constants.ABILITY in split_msg[4]
    #     and other_side.name in split_msg[5]
    #     and split_msg[1] == "-heal"
    # ):
    #     ability = normalize_name(split_msg[4].split(constants.ABILITY)[-1].strip(": "))
    #     logger.info("Setting {}'s ability to: {}".format(pkmn.name, ability))
    #     pkmn.ability = ability

    # give that pokemon an item if this string specifies one
    if len(split_msg) == 5 and constants.ITEM in split_msg[4] and pkmn.item is not None:
        item = normalize_name(split_msg[4].split(constants.ITEM)[-1].strip(": "))
        logger.info("Setting {}'s item to: {}".format(pkmn.name, item))
        pkmn.item = item


def faint(battle, split_msg):
    side, _, slot, active = get_side_slot_active(battle, split_msg)
    active.hp = 0
    if active.name == "dondozo" and "commanded" in active.volatile_statuses:
        if slot.identifier == "a":
            ally = side.slot_b.active
        else:
            ally = side.slot_a.active
        logger.info(
            "{} fainted while commanded, removing commanding from {}".format(
                active.name,
                ally.name,
            )
        )
        remove_volatile(ally, "commanding")


def fail(battle, split_msg):
    # |-fail|p2a: Dragapult|unboost|[from] ability: Clear Body|[of] p2a: Dragapult
    # if (
    #     len(split_msg) > 5
    #     and split_msg[4].startswith("[from] ability: ")
    #     and split_msg[5].startswith("[of]")
    # ):
    #     ability_side = (
    #         battle.user
    #         if split_msg[5].startswith(f"[of] {battle.user.name}")
    #         else battle.opponent
    #     )
    #     ability = normalize_name(split_msg[4].split("ability: ")[-1])
    #     logger.info(
    #         "Setting {}'s ability to: {}".format(ability_side.active.name, ability)
    #     )
    #     ability_side.active.ability = ability
    ...


def move(battle, split_msg):
    side, _, slot, pkmn = get_side_slot_active(battle, split_msg)
    move_name = normalize_name(split_msg[3].strip().lower())

    # zoroark_from_reserves = side.find_pokemon_in_reserves(
    #     "zoroark"
    # ) or side.find_pokemon_in_reserves("zoroarkhisui")

    # in battle factory we can deduce that there is a zoroark in front of us
    # if we see a move that is not in the known moveset and a zoroark is in the reserves
    # if (
    #     is_opponent(battle, split_msg)
    #     and zoroark_from_reserves is not None
    #     and "transform" not in pkmn.volatile_statuses
    #     and battle.battle_type in [constants.BATTLE_FACTORY, constants.STANDARD_BATTLE]
    #     and move_name not in TeamDatasets.get_all_possible_moves(pkmn)
    #     and move_name in TeamDatasets.get_all_possible_moves(zoroark_from_reserves)
    #     and "from" not in split_msg[-1]
    # ):
    #     logger.info(
    #         "{} using {} means it is {}".format(
    #             pkmn.name, move_name, zoroark_from_reserves.name
    #         )
    #     )
    #     _switch_active_with_zoroark_from_reserves(side, zoroark_from_reserves)
    #
    #     # the rest of this function uses `pkmn`, so we need to set it to the correct pkmn
    #     pkmn = zoroark_from_reserves

    # in randombattles we can deduce that there is a zoroark in front of us
    # if we see a move that is not in the known moveset, even if there is no
    # zoroark is in the reserves
    # if (
    #     is_opponent(battle, split_msg)
    #     and battle.battle_type == constants.RANDOM_BATTLE
    #     and "transform" not in pkmn.volatile_statuses
    #     and move_name not in RandomBattleTeamDatasets.get_all_possible_moves(pkmn)
    #     and "from" not in split_msg[-1]
    # ):
    #     actual_zoroark = None
    #     zoroark_hisui = Pokemon("zoroarkhisui", 100)
    #     zoroark_regular = Pokemon("zoroark", 100)
    #     if (
    #         zoroark_from_reserves is not None
    #         and move_name
    #         in RandomBattleTeamDatasets.get_all_possible_moves(zoroark_from_reserves)
    #     ):
    #         actual_zoroark = zoroark_from_reserves
    #
    #     elif (
    #         battle.generation not in constants.NO_TEAM_PREVIEW_GENS
    #         and zoroark_from_reserves is None
    #         and move_name
    #         in RandomBattleTeamDatasets.get_all_possible_moves(zoroark_hisui)
    #     ):
    #         actual_zoroark = zoroark_hisui
    #         actual_zoroark.level = RandomBattleTeamDatasets.predict_set(
    #             actual_zoroark
    #         ).pkmn_set.level
    #         side.reserve.append(actual_zoroark)
    #
    #     elif (
    #         battle.generation not in constants.NO_TEAM_PREVIEW_GENS
    #         and zoroark_from_reserves is None
    #         and move_name
    #         in RandomBattleTeamDatasets.get_all_possible_moves(zoroark_regular)
    #     ):
    #         actual_zoroark = zoroark_regular
    #         actual_zoroark.level = RandomBattleTeamDatasets.predict_set(
    #             actual_zoroark
    #         ).pkmn_set.level
    #         side.reserve.append(actual_zoroark)
    #
    #     if actual_zoroark is not None:
    #         logger.info(
    #             "{} using {} means it is {}".format(
    #                 pkmn.name, move_name, actual_zoroark.name
    #             )
    #         )
    #         _switch_active_with_zoroark_from_reserves(side, actual_zoroark)
    #
    #         # the rest of this function uses `pkmn`, so we need to set it to the correct pkmn
    #         pkmn = actual_zoroark

    # if (
    #     any(msg == "[from]Sleep Talk" for msg in split_msg)
    #     and battle.generation == "gen3"
    # ):
    #     pkmn.gen_3_consecutive_sleep_talks += 1
    #     logger.info(
    #         "{} gen3 consecutive sleep talks: {}".format(
    #             pkmn.name, pkmn.gen_3_consecutive_sleep_talks
    #         )
    #     )
    # elif move_name != "sleeptalk":
    #     pkmn.gen_3_consecutive_sleep_talks = 0

    # gen1 stat modification glitches.
    # swordsdance and agility nullify the effects of burn and paralysis respectively
    # This is implemented by setting a custom volatile
    # if battle.generation == "gen1":
    #     if (
    #         move_name == "swordsdance" or move_name == "meditate"
    #     ) and pkmn.status == constants.BURN:
    #         logger.info(
    #             "{} used swordsdance with burn, nullifying the effects of burn".format(
    #                 pkmn.name
    #             )
    #         )
    #         pkmn.volatile_statuses.append("gen1burnnullify")
    #     elif move_name == "agility" and pkmn.status == constants.PARALYZED:
    #         logger.info(
    #             "{} used agility while paralyzed, nullifying the effects of paralysis".format(
    #                 pkmn.name
    #             )
    #         )
    #         pkmn.volatile_statuses.append("gen1paralysisnullify")

    if split_msg[-1] == "[from]Sleep Talk" or split_msg[-1] == "[from]move: Sleep Talk":
        move_object = pkmn.get_move(move_name)
        if move_object is None:
            pkmn.add_move(move_name)
            logger.info(
                "Added unrevealed {} to {}'s moves because it was called by sleeptalk".format(
                    move_name, pkmn.name
                )
            )
        return

    elif any(
        "[from]" in msg and msg != "[from]lockedmove" and msg != "[from] lockedmove"
        for msg in split_msg
    ):
        if split_msg[-1].startswith("[from] ability:"):
            ability = normalize_name(split_msg[-1].split("ability: ")[-1])
            logger.info("Setting {}'s ability to: {}".format(pkmn.name, ability))
            pkmn.ability = ability
        return

    if "destinybond" in pkmn.volatile_statuses:
        logger.info("Removing destinybond from {}".format(pkmn.name))
        remove_volatile(pkmn, "destinybond")

    if "encore" in pkmn.volatile_statuses:
        pkmn.volatile_status_durations["encore"] += 1
        logger.info(
            "Incrementing encore duration for {} to {}".format(
                pkmn.name, pkmn.volatile_status_durations["encore"]
            )
        )

    if (
        "taunt" in pkmn.volatile_statuses
        and battle.generation not in constants.TAUNT_DURATION_INCREMENT_END_OF_TURN
    ):
        pkmn.volatile_status_durations[constants.TAUNT] += 1
        logger.info(
            "Incrementing taunt duration for {} to {}".format(
                pkmn.name, pkmn.volatile_status_durations[constants.TAUNT]
            )
        )

    # remove volatile status if they have it
    # this is for preparation moves like Phantom Force
    if move_name in pkmn.volatile_statuses:
        logger.info("Removing volatile status {} from {}".format(move_name, pkmn.name))
        remove_volatile(pkmn, move_name)

    if (
        move_name not in constants.PROTECT_VOLATILE_STATUSES
        and slot.active.volatile_status_durations[constants.PROTECT] > 0
    ):
        logger.info(
            "{} used non-protect move, removing protect volatile".format(pkmn.name)
        )
        slot.active.volatile_status_durations[constants.PROTECT] = 0

    if move_name == "struggle":
        logger.info("Not adding struggle to {}'s moves".format(pkmn.name))
        return

    if move_name == "healingwish":
        logger.info(
            "{} used healingwish, setting side_condition to 1".format(pkmn.name)
        )
        side.side_conditions[constants.HEALING_WISH] = 1

    pkmn.moves_used_since_switch_in.add(move_name)

    # add the move to it's moves if it hasn't been seen
    # decrement the PP by one
    # if the move is unknown, do nothing
    # pp_to_decrement = 2 if opposing_pkmn.ability == "pressure" else 1
    move_object = pkmn.get_move(move_name)
    if move_object is None:
        new_move = pkmn.add_move(move_name)
        if new_move is not None:
            new_move.current_pp -= 1
    else:
        move_object.current_pp -= 1
        logger.info(
            "{} already has the move {}. Decrementing the PP by {}".format(
                pkmn.name, move_name, 1
            )
        )

    # if this pokemon used two different moves without switching,
    # set a flag to signify that it cannot have a choice item
    if (
        is_opponent(battle, split_msg)
        and slot.last_used_move.pokemon_name == slot.active.name
        and slot.last_used_move.move != move_name
    ):
        logger.info(
            "{} used two different moves - it cannot have a choice item".format(
                pkmn.name
            )
        )
        pkmn.can_have_choice_item = False
        if pkmn.item in constants.CHOICE_ITEMS and pkmn.item_inferred:
            logger.warning(
                "{} has a choice item, but used two different moves - setting it's item to UNKNOWN".format(
                    pkmn.name
                )
            )
            pkmn.item = constants.UNKNOWN_ITEM

    if unlikely_to_have_choice_item(move_name):
        logger.info(
            "{} using {} makes it unlikely to have a choice item. Setting can_have_choice_item to False".format(
                pkmn.name, move_name
            )
        )
        pkmn.can_have_choice_item = False

    try:
        mv = all_move_json[move_name]
        move_type = mv[constants.TYPE]
        if mv[constants.CATEGORY] != constants.STATUS:
            logger.info(
                "{} used a {} move, removing {}gem from possible items".format(
                    pkmn.name, move_type, move_type
                )
            )
            pkmn.impossible_items.add("{}gem".format(move_type))
    except KeyError:
        pass

    try:
        if (
            all_move_json[move_name][constants.SELF][constants.VOLATILE_STATUS]
            == constants.LOCKED_MOVE
        ):
            logger.info("Adding lockedmove to {}".format(pkmn.name))
            pkmn.volatile_statuses.append(constants.LOCKED_MOVE)
    except KeyError:
        pass

    try:
        if all_move_json[move_name][constants.CATEGORY] == constants.STATUS:
            logger.info(
                "{} used a status-move. Adding `assaultvest` to impossible items".format(
                    pkmn.name
                )
            )
            pkmn.impossible_items.add(constants.ASSAULT_VEST)
    except KeyError:
        pass

    try:
        category = all_move_json[move_name][constants.CATEGORY]
        logger.info("Setting {}'s last used move: {}".format(pkmn.name, move_name))
        if not any(
            "[from]move: Sleep Talk" in msg or "[from]Sleep Talk" in msg
            for msg in split_msg
        ):
            slot.last_used_move = LastUsedMove(
                pokemon_name=pkmn.name, move=move_name, turn=battle.turn
            )
    except KeyError:
        category = None
        if not any(
            "[from]move: Sleep Talk" in msg or "[from]Sleep Talk" in msg
            for msg in split_msg
        ):
            slot.last_used_move = LastUsedMove(
                pokemon_name=pkmn.name, move=constants.DO_NOTHING_MOVE, turn=battle.turn
            )

    # if this pokemon used a damaging move, eliminate the possibility of guessing a lifeorb
    # the lifeorb will reveal itself if it has it
    if category in constants.DAMAGING_CATEGORIES and not any(
        [
            normalize_name(a) in ["sheerforce", "magicguard"]
            for a in pokedex[pkmn.name][constants.ABILITIES].values()
        ]
    ):
        logger.info(
            "{} used a damaging move - not guessing lifeorb anymore".format(pkmn.name)
        )
        pkmn.impossible_items.add(constants.LIFE_ORB)

    # there is nothing special in the protocol for "wish" - it must be extracted here
    if move_name == constants.WISH and "still" not in split_msg[4]:
        logger.info(
            "{} used wish - expecting {} health of recovery next turn".format(
                pkmn.name, pkmn.max_hp / 2
            )
        )
        slot.wish = (2, pkmn.max_hp / 2)

    if move_name == "batonpass":
        slot.baton_passing = True

    # |move|p1a: Slaking|Earthquake|p2a: Heatran
    if pkmn.ability == "truant" or pkmn.name == "slaking":
        if "truant" not in pkmn.volatile_statuses:
            logger.info("Adding 'truant' to {}'s volatiles".format(pkmn.name))
            pkmn.volatile_statuses.append("truant")


def check_stellar_boost(slot: Slot, damage_dealt: DamageDealt):
    mv_dict = all_move_json.get(damage_dealt.move)
    if (
        mv_dict
        and mv_dict[constants.TYPE] not in slot.active.stellar_boosted_types
        and slot.active.terastallized
        and slot.active.tera_type == "stellar"
        and slot.active.name != "terapagosstellar"
    ):
        logger.info(
            "{} did {} damage as stellar, adding {} to steellar_boosted_types".format(
                slot.active.name, mv_dict[constants.TYPE], mv_dict[constants.TYPE]
            )
        )
        slot.active.stellar_boosted_types.append(mv_dict[constants.TYPE])


def setboost(battle, split_msg):
    _, _, _, pkmn = get_side_slot_active(battle, split_msg)
    stat = constants.STAT_ABBREVIATION_LOOKUPS[split_msg[3].strip()]
    amount = int(split_msg[4].strip())
    pkmn.boosts[stat] = amount
    logger.info("Set {}'s {} boost to {}".format(pkmn.name, stat, amount))


def boost(battle, split_msg):
    _, _, _, pkmn = get_side_slot_active(battle, split_msg)

    stat = constants.STAT_ABBREVIATION_LOOKUPS[split_msg[3].strip()]
    amount = int(split_msg[4].strip())

    pkmn.boosts[stat] = min(pkmn.boosts[stat] + amount, constants.MAX_BOOSTS)
    logger.info(
        "{}'s {} was boosted by {} to {}".format(
            pkmn.name, stat, amount, pkmn.boosts[stat]
        )
    )


def unboost(battle, split_msg):
    _, _, _, pkmn = get_side_slot_active(battle, split_msg)

    stat = constants.STAT_ABBREVIATION_LOOKUPS[split_msg[3].strip()]
    amount = int(split_msg[4].strip())
    pkmn.boosts[stat] = max(pkmn.boosts[stat] - amount, -1 * constants.MAX_BOOSTS)
    logger.info(
        "{}'s {} was unboosted by {} to {}".format(
            pkmn.name, stat, amount, pkmn.boosts[stat]
        )
    )


def status(battle, split_msg):
    _, _, _, pkmn = get_side_slot_active(battle, split_msg)

    # if len(split_msg) > 4 and "item: " in split_msg[4]:
    #     pkmn.item = normalize_name(split_msg[4].split("item:")[-1])

    if len(split_msg) == 5 and split_msg[3] == "slp":
        if split_msg[4] == "[from] move: Rest":
            logger.info("Setting rest_turns to 3 for {}".format(pkmn.name))
            pkmn.rest_turns = 3
        else:
            logger.info("Setting sleep_turns to 0 for {}".format(pkmn.name))
            pkmn.sleep_turns = 0

    status_name = split_msg[3].strip()
    logger.info("{} got status: {}".format(pkmn.name, status_name))
    pkmn.status = status_name

    # if status_name is not None:
    #     logger.info(
    #         "No longer guessing lumberry because {} got status {}".format(
    #             pkmn.name, status_name
    #         )
    #     )
    #     pkmn.impossible_items.add("lumberry")

    # ["", "-status", "p1a: Caterpie", "brn", "[from] ability: Flame Body", "[of] p2a: Caterpie"]
    # if (
    #     len(split_msg) > 5
    #     and split_msg[4].startswith("[from] ability: ")
    #     and split_msg[5].startswith("[of]")
    #     and split_msg[5].startswith(f"[of] {other_side.name}")
    # ):
    #     ability = normalize_name(split_msg[4].split("ability: ")[-1])
    #     logger.info("Setting {}'s ability to: {}".format(pkmn.name, ability))
    #     other_side.active.ability = ability


def activate(battle, split_msg):
    side, _, slot, pkmn = get_side_slot_active(battle, split_msg)
    # if is_opponent(battle, split_msg):
    #     pkmn = battle.opponent.active
    #     other_pkmn = battle.user.active
    # else:
    #     pkmn = battle.user.active
    #     other_pkmn = battle.opponent.active

    if (
        normalize_name(split_msg[3]) == constants.SUBSTITUTE
        and split_msg[4] == "[damage]"
    ):
        logger.info(
            "{}'s substitute took damage, setting substitute_hit to True".format(
                pkmn.name
            )
        )
        pkmn.substitute_hit = True

    if split_msg[3] == "ability: Commander":
        if slot.identifier == "a":
            ally = side.slot_b.active
        else:
            ally = side.slot_a.active
        logger.info("{}'s commander activated on {}".format(pkmn.name, ally.name))
        pkmn.volatile_statuses.append("commanding")
        ally.volatile_statuses.append("commanded")

    # if split_msg[3].lower() == "move: poltergeist":
    #     item = normalize_name(split_msg[4])
    #     logger.info("{} has the item {}".format(pkmn.name, item))
    #     pkmn.item = item

    if split_msg[3].lower().startswith("ability: "):
        ability = normalize_name(split_msg[3].split(":")[-1].strip())
        logger.info("Setting {}'s ability to {}".format(pkmn.name, ability))
        pkmn.ability = ability

        # if ability in ["mummy", "lingeringaroma"]:
        #     original_ability = normalize_name(split_msg[4])
        #     other_pkmn.ability = ability
        #     other_pkmn.original_ability = original_ability
        #     logger.info(
        #         "{}'s ability was changed from {} to {}".format(
        #             other_pkmn.name, original_ability, ability
        #         )
        #     )

    # elif split_msg[3].lower().startswith("item: ") and not any(
    #     i == "[consumed]" for i in split_msg
    # ):
    #     item = normalize_name(split_msg[3].split(":")[-1].strip())
    #     logger.info("Setting {}'s item to {}".format(pkmn.name, item))
    #     pkmn.item = item

    if split_msg[3].lower().startswith("move: "):
        move_name = normalize_name(split_msg[3].split(":")[-1].strip())
        if (
            move_name in all_move_json
            and all_move_json[move_name].get("volatileStatus") == "partiallytrapped"
        ):
            logger.info("{} was partially trapped by {}".format(pkmn.name, move_name))
            pkmn.volatile_statuses.append("partiallytrapped")


def anim(battle, split_msg):
    _, _, _, pkmn = get_side_slot_active(battle, split_msg)
    anim_name = normalize_name(split_msg[3].strip())
    if anim_name in pkmn.volatile_statuses:
        logger.info(
            "Removing volatile status {} from {} because of -anim".format(
                anim_name, pkmn.name
            )
        )
        remove_volatile(pkmn, anim_name)


def prepare(battle, split_msg):
    _, _, _, pkmn = get_side_slot_active(battle, split_msg)
    being_prepared = normalize_name(split_msg[3])
    if being_prepared in pkmn.volatile_statuses:
        logger.warning(
            "{} already has the volatile status {}".format(pkmn.name, being_prepared)
        )
    else:
        logger.info(
            "Adding the volatile status {} to {}".format(being_prepared, pkmn.name)
        )
        pkmn.volatile_statuses.append(being_prepared)


def terastallize(battle, split_msg):
    _, _, _, pkmn = get_side_slot_active(battle, split_msg)

    pkmn.terastallized = True
    pkmn.tera_type = normalize_name(split_msg[3])
    logger.info(
        "{} terastallized. Tera type: {}, Original types: {}".format(
            pkmn.name, pkmn.tera_type, pkmn.types
        )
    )


def start_volatile_status(battle, split_msg):
    side, _, slot, pkmn = get_side_slot_active(battle, split_msg)

    volatile_status = normalize_name(split_msg[3].split(":")[-1])

    # for some reason futuresight is sent with the `-start` message
    # `-start` is typically reserved for volatile statuses
    if volatile_status == constants.FUTURE_SIGHT:
        slot.future_sight = (3, pkmn.name)
        return

    if volatile_status.startswith("perish"):
        logger.info(
            "{} got {}. Removing other `perish` volatiles".format(
                pkmn.name, volatile_status
            )
        )
        logger.info("Starting volatiles: {}".format(pkmn.volatile_statuses))
        pkmn.volatile_statuses = [
            vs for vs in pkmn.volatile_statuses if not vs.startswith("perish")
        ]
        pkmn.volatile_statuses.append(volatile_status)
        logger.info("Ending volatiles: {}".format(pkmn.volatile_statuses))
        return

    if volatile_status not in pkmn.volatile_statuses:
        logger.info(
            "Starting the volatile status {} on {}".format(volatile_status, pkmn.name)
        )
        pkmn.volatile_statuses.append(volatile_status)

    if volatile_status == constants.SUBSTITUTE:
        if len(split_msg) >= 5 and split_msg[4] == "[from] move: Shed Tail":
            logger.info(
                "{} started a substitute from shed tail - setting shed_tailing to True".format(
                    pkmn.name
                )
            )
            slot.shed_tailing = True
        logger.info(
            "{} started a substitute - setting substitute_hit to False".format(
                pkmn.name
            )
        )
        pkmn.substitute_hit = False

    if volatile_status == constants.SLOW_START:
        logger.info("{} started slow start - setting slow_start to 6".format(pkmn.name))
        pkmn.volatile_status_durations[constants.SLOW_START] = 6

    if volatile_status == constants.CONFUSION:
        logger.info("{} got confused, no longer guessing lumberry".format(pkmn.name))
        pkmn.impossible_items.add("lumberry")
        if split_msg[-1] == "[fatigue]":
            logger.info(
                "{} got confused from fatigue, removing lockedmove from volatile statuses".format(
                    pkmn.name
                )
            )
            remove_volatile(pkmn, constants.LOCKED_MOVE)
            pkmn.volatile_status_durations[constants.LOCKED_MOVE] = 0

    if volatile_status == constants.DYNAMAX:
        pkmn.hp *= 2
        pkmn.max_hp *= 2
        logger.info(
            "{} started dynamax - doubling their HP to {}/{}".format(
                pkmn.name, pkmn.hp, pkmn.max_hp
            )
        )

    if constants.ABILITY in split_msg[3]:
        pkmn.ability = volatile_status

    if len(split_msg) == 6 and constants.ABILITY in normalize_name(split_msg[5]):
        pkmn.ability = normalize_name(split_msg[5].split("ability:")[-1])

    if volatile_status == constants.TYPECHANGE:
        if split_msg[4] == "[from] move: Reflect Type":
            pkmn_name = normalize_name(split_msg[5].split(":")[-1])
            new_types = deepcopy(pokedex[pkmn_name][constants.TYPES])
        else:
            new_types = [normalize_name(t) for t in split_msg[4].split("/")]

        logger.info("Setting {}'s types to {}".format(pkmn.name, new_types))
        pkmn.types = new_types


def end_volatile_status(battle, split_msg):
    _, _, _, pkmn = get_side_slot_active(battle, split_msg)

    volatile_status = normalize_name(split_msg[3].split(":")[-1])
    if volatile_status == constants.SUBSTITUTE:
        logger.info("Substitute ended for {}".format(pkmn.name))
        pkmn.substitute_hit = False

    if volatile_status == "protosynthesis" or volatile_status == "quarkdrive":
        for vs in pkmn.volatile_statuses:
            if vs.startswith(volatile_status):
                logger.info("Removing {} from {}".format(vs, pkmn.name))
                pkmn.volatile_statuses.remove(vs)
    elif len(split_msg) >= 5 and "partiallytrapped" in split_msg[4]:
        remove_volatile(pkmn, "partiallytrapped")
    elif volatile_status not in pkmn.volatile_statuses:
        logger.warning(
            "{} does not have the volatile status '{}'. Volatiles: {}".format(
                pkmn, volatile_status, pkmn.volatile_statuses
            )
        )
    else:
        logger.info(
            "Removing the volatile status {} from {}".format(volatile_status, pkmn.name)
        )
        remove_volatile(pkmn, volatile_status)
        if volatile_status in pkmn.volatile_status_durations:
            pkmn.volatile_status_durations[volatile_status] = 0
            logger.info(
                "Setting {}'s {} duration to 0".format(pkmn.name, volatile_status)
            )
        if volatile_status == constants.DYNAMAX:
            pkmn.hp /= 2
            pkmn.max_hp /= 2
            logger.info(
                "{} ended dynamax - halving their HP to {}/{}".format(
                    pkmn.name, pkmn.hp, pkmn.max_hp
                )
            )


def curestatus(battle, split_msg):
    side, _, _, _ = get_side_slot_active(battle, split_msg)

    pkmn_name = split_msg[2].split(":")[-1].strip()
    if normalize_name(pkmn_name) == side.slot_a.active.name:
        pkmn = side.slot_a.active
    elif normalize_name(pkmn_name) == side.slot_b.active.name:
        pkmn = side.slot_b.active
    else:
        try:
            pkmn = next(
                filter(lambda x: x.name == normalize_name(pkmn_name), side.reserve)
            )
        except StopIteration:
            logger.warning(
                "The pokemon {} does not exist in the party, defaulting to the active pokemon".format(
                    normalize_name(pkmn_name)
                )
            )
            pkmn = side.slot_a.active

    # even if rest wasn't the cause of sleep, this should be set to 0
    if pkmn.status == constants.SLEEP:
        logger.info(
            "{} is being cured of sleep, setting rest_turns & sleep_turns to 0".format(
                pkmn.name
            )
        )
        pkmn.rest_turns = 0
        pkmn.sleep_turns = 0
    elif pkmn.status == constants.TOXIC:
        side.side_conditions[constants.TOXIC_COUNT] = 0

    pkmn.status = None


def cureteam(battle, split_msg):
    """Cure every pokemon on the opponent's team of it's status"""
    side, _, slot, _ = get_side_slot_active(battle, split_msg)

    side.slot_a.active.status = None
    side.slot_b.active.status = None
    for pkmn in filter(lambda p: isinstance(p, Pokemon), side.reserve):
        pkmn.status = None
        pkmn.rest_turns = 0
        pkmn.sleep_turns = 0


def weather(battle, split_msg):
    # The weather message on its own `|-weather|RainDance` does not contain information about
    #  which side caused it unless it was from an ability
    #  `|-weather|RainDance|[from] ability: Drizzle|[of] p2a: Politoed`
    #
    # If that information is present, we can infer certain things about the Side
    side = None
    slot = None
    if len(split_msg) == 5:
        if battle.opponent.name in split_msg[-1]:
            side = battle.opponent
            if split_msg[-1].startswith("[of] p2a:") or split_msg[-1].startswith(
                "[of] p1a:"
            ):
                slot = side.slot_a
            elif split_msg[-1].startswith("[of] p2b:") or split_msg[-1].startswith(
                "[of] p1b:"
            ):
                slot = side.slot_b
        else:
            side = battle.user
            if split_msg[-1].startswith("[of] p2a:") or split_msg[-1].startswith(
                "[of] p1a:"
            ):
                slot = side.slot_a
            elif split_msg[-1].startswith("[of] p2b:") or split_msg[-1].startswith(
                "[of] p1b:"
            ):
                slot = side.slot_b

    weather_name = normalize_name(split_msg[2].split(":")[-1].strip())
    logger.info("Weather {} is active".format(weather_name))
    battle.weather = weather_name

    if weather_name == "none":
        logger.info("Resetting weather source to None")
        battle.weather_source = None
    # elif side is not None and side_name is not None:
    #     battle.weather_source = f"{side_name}:{side.active.name}"

    if split_msg[-1] == "[upkeep]" and battle.weather_turns_remaining > 0:
        battle.weather_turns_remaining -= 1
    elif split_msg[-1] == "[upkeep]":
        logger.debug("Weather {} permanently active".format(weather_name))
    elif (
        slot is not None
        and weather_name == constants.SUN
        and slot.active.item == "heatrock"
    ):
        logger.info("{} has heatrock, assuming 8 turns of sun".format(slot.active.name))
        battle.weather_turns_remaining = 8
    elif (
        slot is not None
        and weather_name == constants.RAIN
        and slot.active.item == "damprock"
    ):
        logger.info(
            "{} has damprock, assuming 8 turns of rain".format(slot.active.name)
        )
        battle.weather_turns_remaining = 8
    elif (
        slot is not None
        and weather_name == constants.SAND
        and slot.active.item == "smoothrock"
    ):
        logger.info(
            "{} has smoothrock, assuming 8 turns of sand".format(slot.active.name)
        )
        battle.weather_turns_remaining = 8
    elif (
        side is not None
        and weather_name in constants.HAIL_OR_SNOW
        and slot.active.item == "icyrock"
    ):
        logger.info("{} has icyrock, assuming 8 turns of hail".format(slot.active.name))
        battle.weather_turns_remaining = 8
    else:
        battle.weather_turns_remaining = 5

    logger.info("Weather turns remaining: {}".format(battle.weather_turns_remaining))
    if battle.weather_turns_remaining == 0:
        logger.info(
            "Weather {} did not end when expected, giving 3 more turns".format(
                weather_name
            )
        )
        battle.weather_turns_remaining = 3
    #     if (
    #         battle.weather_source is not None
    #         and battle.weather_source != ""
    #         and battle.weather_source.startswith("opponent")
    #     ):
    #         side = battle.opponent
    #         pkmn_name = battle.weather_source.split(":")[-1]
    #         pkmn = (
    #             side.active
    #             if side.active.name == pkmn_name
    #             else side.find_pokemon_in_reserves(pkmn_name)
    #         )
    #         if pkmn is not None and pkmn.item == constants.UNKNOWN_ITEM:
    #             if weather_name == constants.SUN:
    #                 item = "heatrock"
    #             elif weather_name == constants.RAIN:
    #                 item = "damprock"
    #             elif weather_name == constants.SAND:
    #                 item = "smoothrock"
    #             elif weather_name in constants.HAIL_OR_SNOW:
    #                 item = "icyrock"
    #             else:
    #                 item = constants.UNKNOWN_ITEM
    #
    #             logger.info(
    #                 "Weather not ending means that opponent's {} has a {}".format(
    #                     pkmn.name, item
    #                 )
    #             )
    #             pkmn.item = item
    #
    # if side is not None and len(split_msg) >= 5 and side.name in split_msg[4]:
    #     ability = normalize_name(split_msg[3].split(":")[-1].strip())
    #     logger.info("Setting {} ability to {}".format(side.active.name, ability))
    #     side.active.ability = ability


def fieldstart(battle, split_msg):
    """Set the battle's field condition"""
    field_name = normalize_name(split_msg[2].split(":")[-1].strip())

    # some field effects show up as a `-fieldstart` item but are separate from the other fields
    if field_name == constants.TRICK_ROOM:
        logger.info("Setting trickroom")
        battle.trick_room = True
        battle.trick_room_turns_remaining = 5
    elif field_name == constants.GRAVITY:
        logger.info("Setting gravity")
        battle.gravity = True
    else:
        logger.info("Setting the field to {}".format(field_name))
        battle.field = field_name
        battle.field_turns_remaining = 5


def fieldend(battle, split_msg):
    """Remove the battle's field condition"""
    field_name = normalize_name(split_msg[2].split(":")[-1].strip())

    # some field effects show up as a `-fieldend` item but are separate from the other fields
    if field_name == constants.TRICK_ROOM:
        logger.info("Removing trick room")
        battle.trick_room = False
        battle.trick_room_turns_remaining = 0
    elif field_name == constants.GRAVITY:
        logger.info("Removing gravity")
        battle.gravity = False
    else:
        logger.info("Setting the field to None")
        battle.field = None
        battle.field_turns_remaining = 0


def sidestart(battle, split_msg):
    # Inconsistencies in the protocol mean parse after the `:` to get the side condition
    # |-sidestart|p2: Name|Reflect
    # |-sidestart|p2: Name|move: Light Screen
    # |-sidestart|p2: Name|Spikes
    # |-sidestart|p1: Name|move: Stealth Rock
    #
    # Some side conditions have an explicit duration such as lightscreen, reflect, etc.
    # Others are incremented by 1

    condition = split_msg[3].split(":")[-1].strip()
    condition = normalize_name(condition)
    side, _, _, _ = get_side_slot_active(battle, split_msg)

    if condition in SIDE_CONDITION_DEFAULT_DURATION:
        increment_amount = SIDE_CONDITION_DEFAULT_DURATION[condition]
        if condition in ["reflect", "lightscreen", "auroraveil"] and (
            side.slot_a.active.item == "lightclay"
            or side.slot_b.active.item == "lightclay"
        ):
            increment_amount += 3

        side.side_conditions[condition] = increment_amount
        logger.info(
            "Setting side condition {} to {} for {}".format(
                condition, SIDE_CONDITION_DEFAULT_DURATION[condition], side.name
            )
        )
    else:
        side.side_conditions[condition] += 1
        logger.info(
            "Incremented side condition {} to {} for {}".format(
                condition, side.side_conditions[condition], side.name
            )
        )


def sideend(battle, split_msg):
    """Remove a side effect such as stealth rock or sticky web"""
    condition = split_msg[3].split(":")[-1].strip()
    condition = normalize_name(condition)

    if is_opponent(battle, split_msg):
        logger.info("Side condition {} ending for opponent".format(condition))
        battle.opponent.side_conditions[condition] = 0
    else:
        logger.info("Side condition {} ending for user".format(condition))
        battle.user.side_conditions[condition] = 0


def swapsideconditions(battle, _):
    user_sc = battle.user.side_conditions
    opponent_sc = battle.opponent.side_conditions
    for side_condition in constants.COURT_CHANGE_SWAPS:
        user_sc[side_condition], opponent_sc[side_condition] = (
            opponent_sc[side_condition],
            user_sc[side_condition],
        )


def set_item(battle, split_msg):
    """Set the opponent's item"""
    side, _, slot, pkmn = get_side_slot_active(battle, split_msg)
    item = normalize_name(split_msg[3].strip())
    pkmn.item = item

    # if (
    #     len(split_msg) >= 5
    #     and side.active.removed_item is None
    #     and item != side.active.item
    #     and side.active.item not in [constants.UNKNOWN_ITEM]
    # ):
    #     logger.info("{}'s removed item is {}".format(side.active.name, item))
    #     side.active.removed_item = side.active.item

    # when the bot gets tricked we set the opponent's removed item
    # if (
    #     len(split_msg) >= 5
    #     and "[from] move: Trick" in split_msg[4]
    #     and not is_opponent(battle, split_msg)
    #     and other_side.active.removed_item is None
    # ):
    #     logger.info("Setting opponent's removed_item to {}".format(item))
    #     other_side.active.removed_item = item

    # for gen5 frisk only
    # the frisk message will (incorrectly imo) show the item as belonging to the
    # pokemon with frisk
    #
    # e.g. Furret is frisking the opponent:
    # |-item|p2a: Furret|Life Orb|[from] ability: Frisk|[of] p2a: Furret
    # if (
    #     len(split_msg) == 6
    #     and split_msg[4] == "[from] ability: Frisk"
    #     and split_msg[2] in split_msg[5]
    # ):
    #     logger.info(
    #         "{} frisked the opponent's item as {}".format(side.active.name, item)
    #     )
    #     logger.info("Setting {}'s item to {}".format(other_side.active.name, item))
    #     other_side.active.item = item
    # else:
    #     logger.info("Setting {}'s item to {}".format(side.active.name, item))
    #     side.active.item = item


def remove_item(battle, split_msg):
    """Remove the opponent's item"""
    _, _, slot, _ = get_side_slot_active(battle, split_msg)

    item = normalize_name(split_msg[3].strip())
    logger.info("Removing {}'s item: {}".format(slot.active.name, item))
    slot.active.item = None

    if slot.active.removed_item is None:
        logger.info("Setting {}'s removed item to {}".format(slot.active.name, item))
        slot.active.removed_item = item

    if "unburden" not in slot.active.volatile_statuses and "unburden" in [
        normalize_name(a)
        for a in pokedex[slot.active.name][constants.ABILITIES].values()
    ]:
        logger.info("Adding unburden volatile to {}".format(slot.active.name))
        slot.active.volatile_statuses.append("unburden")

    if len(split_msg) >= 5 and "knockoff" in normalize_name(split_msg[4]):
        logger.info("Knockoff removed {}'s item".format(slot.active.name))
        slot.active.knocked_off = True


def immune(battle, split_msg):
    ...
    # side, _, slot, pkmn = get_side_slot_active(battle, split_msg)
    #
    # if is_opponent(battle, split_msg):
    #     side = battle.opponent
    #     pkmn = slot.active
    # else:
    #     side = battle.user
    #     pkmn = slot.active
    #
    # for msg in split_msg:
    #     if constants.ABILITY in normalize_name(msg):
    #         ability = normalize_name(msg.split(":")[-1])
    #         logger.info("Setting {}'s ability to {}".format(pkmn.name, ability))
    #         pkmn.ability = ability

    # zoroark_from_reserves = side.find_pokemon_in_reserves(
    #     "zoroark"
    # ) or side.find_pokemon_in_reserves("zoroarkhisui")
    #
    # expected_damage_rolls, _ = poke_engine_get_damage_rolls(
    #     deepcopy(battle), battle.user.last_used_move.move, "none", True
    # )

    # Zoroark checks
    # if (
    #     is_opponent(battle, split_msg)
    #     and not side.active.name.startswith("zoroark")
    #     and battle.user.last_used_move.move in all_move_json
    #     and all_move_json[battle.user.last_used_move.move][constants.CATEGORY]
    #     != constants.STATUS
    #     and type_effectiveness_modifier(
    #         all_move_json[battle.user.last_used_move.move][constants.TYPE],
    #         side.active.types,
    #     )
    #     != 0
    #     and "from" not in split_msg[-1]
    #     and not all(x == 0 for x in expected_damage_rolls)
    #     and battle.user.future_sight[0] != 1
    #     and not (
    #         side.active.terastallized
    #         and type_effectiveness_modifier(
    #             all_move_json[battle.user.last_used_move.move][constants.TYPE],
    #             [side.active.tera_type],
    #         )
    #         == 0
    #     )
    # ):
    #     # Battle Factory: Zoroark must be in the reserves
    #     # and must be immune to the last used move by the bot
    #     if (
    #         battle.battle_type == constants.BATTLE_FACTORY
    #         and zoroark_from_reserves is not None
    #         and type_effectiveness_modifier(
    #             all_move_json[battle.user.last_used_move.move][constants.TYPE],
    #             zoroark_from_reserves.types,
    #         )
    #         == 0
    #     ):
    #         logger.info(
    #             "{} was immune to {} when it shouldn't be - it is {}".format(
    #                 pkmn.name,
    #                 battle.user.last_used_move.move,
    #                 zoroark_from_reserves.name,
    #             )
    #         )
    #         _switch_active_with_zoroark_from_reserves(side, zoroark_from_reserves)
    #
    #     # Random Battle: Zoroark may be in the reserves so we need to check the move type
    #     # that it was immune to
    #     elif battle.battle_type == constants.RANDOM_BATTLE:
    #         actual_zoroark = None
    #         zoroark_hisui = Pokemon("zoroarkhisui", 100)
    #         zoroark_regular = Pokemon("zoroark", 100)
    #
    #         # zoroark was in the reserves - just use that one
    #         if (
    #             zoroark_from_reserves is not None
    #             and type_effectiveness_modifier(
    #                 all_move_json[battle.user.last_used_move.move][constants.TYPE],
    #                 zoroark_from_reserves.types,
    #             )
    #             == 0
    #         ):
    #             actual_zoroark = zoroark_from_reserves
    #
    #         # hisui zoroark
    #         elif (
    #             zoroark_from_reserves is None
    #             and type_effectiveness_modifier(
    #                 all_move_json[battle.user.last_used_move.move][constants.TYPE],
    #                 zoroark_hisui.types,
    #             )
    #             == 0
    #             and zoroark_hisui.name in RandomBattleTeamDatasets.pkmn_sets
    #         ):
    #             actual_zoroark = zoroark_hisui
    #             actual_zoroark.level = RandomBattleTeamDatasets.predict_set(
    #                 actual_zoroark
    #             ).pkmn_set.level
    #             side.reserve.append(actual_zoroark)
    #
    #         # regular zoroark
    #         elif (
    #             zoroark_from_reserves is None
    #             and type_effectiveness_modifier(
    #                 all_move_json[battle.user.last_used_move.move][constants.TYPE],
    #                 zoroark_regular.types,
    #             )
    #             == 0
    #             and zoroark_regular.name in RandomBattleTeamDatasets.pkmn_sets
    #         ):
    #             actual_zoroark = zoroark_regular
    #             actual_zoroark.level = RandomBattleTeamDatasets.predict_set(
    #                 actual_zoroark
    #             ).pkmn_set.level
    #             side.reserve.append(actual_zoroark)
    #
    #         # if we found a zoroark from one of those branches
    #         if actual_zoroark is not None:
    #             logger.info(
    #                 "{} was immune to {} when it shouldn't be - it is {}".format(
    #                     pkmn.name,
    #                     battle.user.last_used_move.move,
    #                     actual_zoroark.name,
    #                 )
    #             )
    #             _switch_active_with_zoroark_from_reserves(side, actual_zoroark)


# def _switch_active_with_zoroark_from_reserves(
#     opponent_side: Battler, zoroark_from_reserves: Pokemon
# ):
#     """
#     This is called when we are 100% sure that the opponent's active pkmn is a zoroark
#     This swaps the active pkmn with the zoroark from the reserves
#
#     Assumptions:
#         - The `zoroark_from_reserves` MUST be in `opponent_side.reserve`
#     """
#     pkmn = opponent_side.active
#
#     # any moves used by this pkmn since switching in need to be removed because we cannot guarantee that they
#     # belong to this pkmn
#     for mv in pkmn.moves_used_since_switch_in:
#         logger.info(
#             "Removing {} from {}'s moves because it is {}".format(
#                 mv, pkmn.name, zoroark_from_reserves.name
#             )
#         )
#         pkmn.remove_move(mv)
#         if zoroark_from_reserves.get_move(mv) is None:
#             zoroark_from_reserves.add_move(mv)
#
#     # set attributes on zoroark that were on the pokemon that we thought was zoroark
#     # and clear those attributes from the pokemon that we thought was zoroark
#     pkmn_hp_percent = float(pkmn.hp) / pkmn.max_hp
#     zoroark_from_reserves.hp = zoroark_from_reserves.max_hp * pkmn_hp_percent
#     zoroark_from_reserves.boosts = copy(pkmn.boosts)
#     zoroark_from_reserves.status = pkmn.status
#     zoroark_from_reserves.volatile_statuses = copy(pkmn.volatile_statuses)
#     zoroark_from_reserves.terastallized = pkmn.terastallized
#     zoroark_from_reserves.tera_type = pkmn.tera_type
#     pkmn.boosts.clear()
#     pkmn.status = None
#     pkmn.volatile_statuses.clear()
#     pkmn.volatile_status_durations.clear()
#
#     if pkmn.terastallized:
#         pkmn.terastallized = False
#         pkmn.tera_type = None
#
#     zoroark_from_reserves.zoroark_disguised_as = pkmn.name
#
#     # swap the pkmn places
#     opponent_side.reserve.append(pkmn)
#     opponent_side.active = zoroark_from_reserves
#     opponent_side.reserve.remove(zoroark_from_reserves)


def update_ability(battle, split_msg):
    _, _, slot, pkmn = get_side_slot_active(battle, split_msg)
    ability = normalize_name(split_msg[3])
    if len(split_msg) >= 6 and "ability:" in split_msg[4]:
        original_ability = normalize_name(split_msg[4].split(":")[-1])
        logger.info(
            "Setting {}'s original ability to {}".format(pkmn.name, original_ability)
        )
        pkmn.original_ability = original_ability

        # if split_msg[5].startswith("[of]") and other_side.name in split_msg[5]:
        #     logger.info(
        #         "Setting {}'s ability to {}".format(other_side.active.name, ability)
        #     )
        #     other_side.active.ability = ability
    elif ability == "asone":
        if pkmn.name == "calyrexice":
            ability = "asoneglastrier"
        elif pkmn.name == "calyrexshadow":
            ability = "asonespectrier"
        else:
            logger.warning(
                "Unknown asone ability for {} - defaulting to asoneglastrier".format(
                    pkmn.name
                )
            )
            ability = "asoneglastrier"
    elif pkmn.ability in ["asoneglastrier", "asonespectrier"]:
        logger.info(
            "{} has the ability {}, will not change to {}".format(
                pkmn.name, pkmn.ability, ability
            )
        )
        ability = pkmn.ability

    logger.info("Setting {}'s ability to {}".format(pkmn.name, ability))
    pkmn.ability = ability


def illusion_end(battle, split_msg):
    side, _, slot, pkmn = get_side_slot_active(battle, split_msg)

    if (
        is_opponent(battle, split_msg)
        and slot.active.name not in ["zoroark", "zoroarkhisui"]
        and slot.active.zoroark_disguised_as is None
    ):
        logger.info("Illusion ending for opponent")
        hp_percent = float(slot.active.hp) / slot.active.max_hp
        previous_boosts = slot.active.boosts
        previous_status = slot.active.status
        previous_item = slot.active.item

        zoroark_from_switch_string = Pokemon.from_switch_string(split_msg[3])
        zoroark_reserve_index = None
        for index, pkmn in enumerate(side.reserve):
            if pkmn == zoroark_from_switch_string:
                zoroark_reserve_index = index
                break

        pkmn_disguised_as = slot.active
        pkmn_disguised_as.item = constants.UNKNOWN_ITEM
        side.reserve.append(pkmn_disguised_as)
        if zoroark_reserve_index is not None:
            reserve_zoroark = side.reserve.pop(zoroark_reserve_index)
            slot.active = reserve_zoroark
        else:
            slot.active = zoroark_from_switch_string

        # the moves that have been used since this pkmn switched-in need
        # to be un-associated with the pkmn being disguised as and need to
        # be associated with the new pkmn instead
        for mv in pkmn_disguised_as.moves_used_since_switch_in:
            pkmn_disguised_as.remove_move(mv)
            if slot.active.get_move(mv) is None:
                slot.active.add_move(mv)

        # the pokemon that we thought was active needs some attributes reset to
        # whatever the values were at switch-in as any changes that happened to zoroark
        # since switching in have not happened to the actual pokemon
        if pkmn_disguised_as.hp_at_switch_in != pkmn_disguised_as.hp:
            logger.info(
                "Resetting {}'s HP {} to its value at switch-in: {}/{} ({}%)".format(
                    pkmn_disguised_as.name,
                    int(pkmn_disguised_as.hp),
                    pkmn_disguised_as.hp_at_switch_in,
                    pkmn_disguised_as.max_hp,
                    round(
                        100
                        * pkmn_disguised_as.hp_at_switch_in
                        / pkmn_disguised_as.max_hp,
                        1,
                    ),
                )
            )
            pkmn_disguised_as.hp = pkmn_disguised_as.hp_at_switch_in
        if pkmn_disguised_as.status_at_switch_in != pkmn_disguised_as.status:
            logger.info(
                "Resetting {}'s status {} to its value at switch-in: {}".format(
                    pkmn_disguised_as.name,
                    pkmn_disguised_as.status,
                    pkmn_disguised_as.status_at_switch_in,
                )
            )
            pkmn_disguised_as.status = pkmn_disguised_as.status_at_switch_in

        slot.active.hp = hp_percent * slot.active.max_hp
        slot.active.boosts = previous_boosts
        slot.active.status = previous_status
        slot.active.item = previous_item

    slot.active.zoroark_disguised_as = None


def form_change(battle, split_msg):
    if is_opponent(battle, split_msg):
        is_user = False
    else:
        is_user = True

    if split_msg[-1] == "[silent]":
        logger.info("Silent form change, not updating the active pokemon")
        return

    side, other_side, slot, pkmn = get_side_slot_active(battle, split_msg)
    logger.info("Form Change: {} -> {}".format(slot.active.name, split_msg[3]))
    slot.active.forme_change(split_msg[3])

    # the protocol doesn't show terapagos' ability changing to terashell
    if slot.active.name == "terapagosterastal":
        slot.active.ability = "terashell"

    if is_user:
        slot.re_initialize_active_pokemon_from_request_json(battle.request_json)


def zpower(battle, split_msg):
    _, _, slot, _ = get_side_slot_active(battle, split_msg)
    logger.info("{} Used a Z-Move, setting item to None".format(slot.active.name))
    slot.active.item = None


def clearnegativeboost(battle, split_msg):
    _, _, _, pkmn = get_side_slot_active(battle, split_msg)

    for stat, value in pkmn.boosts.items():
        if value < 0:
            logger.info("Setting {}'s {} boost to 0".format(pkmn.name, stat))
            pkmn.boosts[stat] = 0


def clearboost(battle, split_msg):
    _, _, _, pkmn = get_side_slot_active(battle, split_msg)
    for stat, value in pkmn.boosts.items():
        logger.info("Setting {}'s {} boost to 0".format(pkmn.name, stat))
        pkmn.boosts[stat] = 0


def clearallboost(battle, _):
    pkmn = battle.user.slot_a.active
    for stat, value in pkmn.boosts.items():
        if value != 0:
            logger.info("Setting {}'s {} boost to 0".format(pkmn.name, stat))
            pkmn.boosts[stat] = 0

    pkmn = battle.user.slot_b.active
    for stat, value in pkmn.boosts.items():
        if value != 0:
            logger.info("Setting {}'s {} boost to 0".format(pkmn.name, stat))
            pkmn.boosts[stat] = 0

    pkmn = battle.opponent.slot_a.active
    for stat, value in pkmn.boosts.items():
        if value != 0:
            logger.info("Setting {}'s {} boost to 0".format(pkmn.name, stat))
            pkmn.boosts[stat] = 0

    pkmn = battle.opponent.slot_b.active
    for stat, value in pkmn.boosts.items():
        if value != 0:
            logger.info("Setting {}'s {} boost to 0".format(pkmn.name, stat))
            pkmn.boosts[stat] = 0


def singleturn(battle, split_msg):
    side, _, slot, pkmn = get_side_slot_active(battle, split_msg)
    move_name = normalize_name(split_msg[3].split(":")[-1])
    if move_name in constants.PROTECT_VOLATILE_STATUSES:
        # increment by 2 because the `upkeep` function will decrement by 1 on every end-of-turn
        # increment by 2 and not set to 2 because a double protect could have happened
        slot.active.volatile_status_durations[constants.PROTECT] += 2
        logger.info(
            "{} used a protect move, set protect duration to {}".format(
                pkmn.name, slot.active.volatile_status_durations[constants.PROTECT]
            )
        )

    # |-singleturn|p1a: Skarmory|move: Roost
    elif move_name == constants.ROOST:
        # set to 2 because the `upkeep` function will decrement by 1 on every end-of-turn
        pkmn.volatile_statuses.append(constants.ROOST)
        logger.info("{} has acquired the 'roost' volatilestatus".format(pkmn.name))

    elif move_name == "helpinghand":
        pkmn.volatile_statuses.append("helpinghand")
        logger.info("{} gets Helping Hand".format(pkmn.name))


def mustrecharge(battle, split_msg):
    # Bot's side does not get mustrecharge because the request JSON
    # will contain the only available `recharge` move
    _, _, _, pkmn = get_side_slot_active(battle, split_msg)
    if is_opponent(battle, split_msg):
        logger.info("{} must recharge".format(pkmn.name))
        pkmn.volatile_statuses.append("mustrecharge")

    # Truant and mustrecharge together means that you only recharge next turn
    if "truant" in pkmn.volatile_statuses:
        logger.info("{} must recharge with truant, removing truant".format(pkmn.name))
        remove_volatile(pkmn, "truant")


def cant(battle, split_msg):
    if is_opponent(battle, split_msg):
        opponent = True
    else:
        opponent = False

    _, _, slot, _ = get_side_slot_active(battle, split_msg)

    if slot.last_used_move.move.startswith("switch"):
        # if we just switched in but got `cant`, we need to set last used move
        # to `none` so that we cannot use moves like fakeout/firstimpression
        slot.last_used_move = LastUsedMove(
            pokemon_name=slot.active.name,
            move="move:none",
            turn=battle.turn,
        )
    else:
        slot.last_used_move = LastUsedMove(
            pokemon_name=slot.active.name,
            move=slot.last_used_move.move,
            turn=battle.turn,
        )

    # |cant|p1a: Slaking|ability: Truant
    if len(split_msg) == 4 and split_msg[3] == "ability: Truant":
        logger.info(
            "{} got 'cant' from truant, removing truant volatile".format(
                slot.active.name
            )
        )
        remove_volatile(slot.active, "truant")

    # |cant|p2a: Tauros|recharge
    if len(split_msg) == 4 and split_msg[3] == "recharge":
        logger.info(
            "{} got 'cant' from recharge, removing mustrecharge volatile".format(
                slot.active.name
            )
        )
        if opponent and "mustrecharge" not in slot.active.volatile_statuses:
            logger.warning(
                "{} did not have mustrecharge but recharged".format(slot.active.name)
            )

        remove_volatile(slot.active, "mustrecharge")

    # |cant|p2a: Politoed|move: Taunt|Toxic
    if len(split_msg) == 4 and split_msg[3].startswith("move: "):
        move_name = normalize_name(split_msg[3].split(":")[-1])
        move_object = slot.active.get_move(move_name)
        if move_object is None:
            slot.active.add_move(move_name)
            logger.info(
                "Adding {} to {}'s moves from 'cant'".format(
                    move_name, slot.active.name
                )
            )

    if len(split_msg) == 4 and split_msg[3] == constants.SLEEP:
        logger.info("{} got 'cant' from sleep".format(slot.active.name))
        if slot.active.rest_turns > 1:
            slot.active.rest_turns -= 1
            logger.info(
                "Decrementing {}'s rest_turns to {}".format(
                    slot.active.name, slot.active.rest_turns
                )
            )
        elif slot.active.rest_turns == 1:
            logger.critical(
                "{} has rest_turns==1 and got 'cant' from sleep".format(
                    slot.active.name
                )
            )
            exit(1)
        else:
            slot.active.sleep_turns += 1
            logger.info(
                "Incrementing {}'s sleep_turns to {}".format(
                    slot.active.name, slot.active.sleep_turns
                )
            )


def upkeep(battle, _):
    if battle.trick_room:
        battle.trick_room_turns_remaining -= 1
        logger.info(
            "Trick Room turns remaining: {}".format(battle.trick_room_turns_remaining)
        )

    if battle.field is not None and battle.field_turns_remaining > 0:
        battle.field_turns_remaining -= 1
        logger.info(
            "{} turns remaining: {}".format(battle.field, battle.field_turns_remaining)
        )

    if battle.field is not None and battle.field_turns_remaining == 0:
        logger.info(
            "{} did not end when expected, giving 3 more turns".format(battle.field)
        )
        battle.field_turns_remaining = 3

    if constants.ROOST in battle.user.slot_a.active.volatile_statuses:
        logger.info(
            "Removing 'roost' from {}'s volatiles".format(
                battle.user.slot_a.active.name
            )
        )
        battle.user.slot_a.active.volatile_statuses = [
            v
            for v in battle.user.slot_a.active.volatile_statuses
            if v != constants.ROOST
        ]
    if constants.ROOST in battle.user.slot_b.active.volatile_statuses:
        logger.info(
            "Removing 'roost' from {}'s volatiles".format(
                battle.user.slot_b.active.name
            )
        )
        battle.user.slot_b.active.volatile_statuses = [
            v
            for v in battle.user.slot_b.active.volatile_statuses
            if v != constants.ROOST
        ]

    if constants.ROOST in battle.opponent.slot_a.active.volatile_statuses:
        logger.info(
            "Removing 'roost' from {}'s volatiles".format(
                battle.opponent.slot_a.active.name
            )
        )
        battle.opponent.slot_a.active.volatile_statuses = [
            v
            for v in battle.opponent.slot_a.active.volatile_statuses
            if v != constants.ROOST
        ]

    if constants.ROOST in battle.opponent.slot_b.active.volatile_statuses:
        logger.info(
            "Removing 'roost' from {}'s volatiles".format(
                battle.opponent.slot_b.active.name
            )
        )
        battle.opponent.slot_b.active.volatile_statuses = [
            v
            for v in battle.opponent.slot_b.active.volatile_statuses
            if v != constants.ROOST
        ]

    for slot in [
        battle.user.slot_a,
        battle.user.slot_b,
        battle.opponent.slot_a,
        battle.opponent.slot_b,
    ]:
        remove_volatile(slot.active, "helpinghand")

        if slot.active.volatile_status_durations[constants.PROTECT] > 0:
            slot.active.volatile_status_durations[constants.PROTECT] -= 1
            logger.info(
                "Decrementing protect duration for {} to {}".format(
                    slot.active,
                    slot.active.volatile_status_durations[constants.PROTECT],
                )
            )

        if constants.LOCKED_MOVE in slot.active.volatile_statuses:
            slot.active.volatile_status_durations[constants.LOCKED_MOVE] += 1
            logger.info(
                "Incremented lockedmove for {} to {}".format(
                    slot.active,
                    slot.active.volatile_status_durations[constants.LOCKED_MOVE],
                )
            )

        pkmn = slot.active
        if constants.YAWN in pkmn.volatile_statuses:
            previous_duration = pkmn.volatile_status_durations[constants.YAWN]
            if previous_duration == 0:
                pkmn.volatile_status_durations[constants.YAWN] = 1
            elif previous_duration == 1:
                pkmn.volatile_status_durations[constants.YAWN] = 0
                remove_volatile(pkmn, constants.YAWN)
                logger.info("Removed yawn volatile from {}".format(pkmn.name))
            else:
                raise ValueError(
                    "Got yawn duration {} for {}".format(previous_duration, pkmn.name)
                )
            logger.info(
                "{} had yawn at the end of the turn, changed duration from {} to {}".format(
                    pkmn.name,
                    previous_duration,
                    pkmn.volatile_status_durations[constants.YAWN],
                )
            )
        if constants.SLOW_START in pkmn.volatile_statuses:
            pkmn.volatile_status_durations[constants.SLOW_START] -= 1
            logger.info(
                "Decremented slow start duration for {} to {}".format(
                    pkmn.name, pkmn.volatile_status_durations[constants.SLOW_START]
                )
            )

        if slot.wish[0] > 0:
            slot.wish = (slot.wish[0] - 1, slot.wish[1])
            logger.info("Decrementing wish to {}".format(slot.wish[0]))

        if slot.future_sight[0] > 0:
            slot.future_sight = (
                slot.future_sight[0] - 1,
                slot.future_sight[1],
            )
            logger.info("Decrementing future_sight to {}".format(slot.future_sight[0]))

    for side in [battle.user, battle.opponent]:
        side_string = "opponent" if side == battle.opponent else "user"

        if side.side_conditions[constants.REFLECT] > 0:
            side.side_conditions[constants.REFLECT] -= 1
            logger.info(
                "Decrementing reflect for {} to {}".format(
                    side_string, side.side_conditions[constants.REFLECT]
                )
            )
            if side.side_conditions[constants.REFLECT] == 0:
                logger.info(
                    "reflect did not end for {} when expected, giving it 3 more turns".format(
                        side_string
                    )
                )
                side.side_conditions[constants.REFLECT] = 3

        if side.side_conditions[constants.LIGHT_SCREEN] > 0:
            side.side_conditions[constants.LIGHT_SCREEN] -= 1
            logger.info(
                "Decrementing lightscreen for {} to {}".format(
                    side_string, side.side_conditions[constants.LIGHT_SCREEN]
                )
            )
            if side.side_conditions[constants.LIGHT_SCREEN] == 0:
                logger.info(
                    "lightscreen did not end for {} when expected, giving it 3 more turns".format(
                        side_string
                    )
                )
                side.side_conditions[constants.LIGHT_SCREEN] = 3

        if side.side_conditions[constants.AURORA_VEIL] > 0:
            side.side_conditions[constants.AURORA_VEIL] -= 1
            logger.info(
                "Decrementing auroraveil for {} to {}".format(
                    side_string, side.side_conditions[constants.AURORA_VEIL]
                )
            )
            if side.side_conditions[constants.AURORA_VEIL] == 0:
                logger.info(
                    "auroraveil did not end for {} when expected, giving it 3 more turns".format(
                        side_string
                    )
                )
                side.side_conditions[constants.AURORA_VEIL] = 3

        if side.side_conditions[constants.TAILWIND] > 0:
            side.side_conditions[constants.TAILWIND] -= 1
            logger.info(
                "Decrementing tailwind for {} to {}".format(
                    side_string, side.side_conditions[constants.TAILWIND]
                )
            )

        if side.side_conditions[constants.MIST] > 0:
            side.side_conditions[constants.MIST] -= 1
            logger.info(
                "Decrementing mist for {} to {}".format(
                    side_string, side.side_conditions[constants.MIST]
                )
            )

        if side.side_conditions[constants.SAFEGUARD] > 0:
            side.side_conditions[constants.SAFEGUARD] -= 1
            logger.info(
                "Decrementing safeguard for {} to {}".format(
                    side_string, side.side_conditions[constants.SAFEGUARD]
                )
            )

    # If a pkmn has less than maxhp during upkeep,
    # we do not want to guess leftovers/blacksludge anymore when it is time to guess an item
    # leftovers and blacksludge will reveal themselves at the end of the turn if they exist
    # opp_pkmn = battle.opponent.active
    # if opp_pkmn.hp < opp_pkmn.max_hp:
    #     logger.info(
    #         "{} has less than maxhp during upkeep, no longer guessing leftovers or blacksludge".format(
    #             opp_pkmn.name
    #         )
    #     )
    #     opp_pkmn.impossible_items.add(constants.LEFTOVERS)
    #     opp_pkmn.impossible_items.add(constants.BLACK_SLUDGE)
    #
    # if opp_pkmn.status is None:
    #     opp_pkmn.impossible_items.add("flameorb")
    #     opp_pkmn.impossible_items.add("toxicorb")


def mega(battle, split_msg):
    _, _, slot, _ = get_side_slot_active(battle, split_msg)

    slot.active.is_mega = True
    logger.info("Mega-Pokemon: {}".format(slot.active.name))


def transform(battle, split_msg):
    ...
    # if is_opponent(battle, split_msg):
    #     side = battle.opponent
    #     other_side = battle.user
    # else:
    #     side = battle.user
    #     other_side = battle.opponent

    # transformed_into_name = other_side.active.name
    # logger.info(
    #     "{} transformed into {}".format(side.active.name, transformed_into_name)
    # )
    # side.active.boosts = deepcopy(other_side.active.boosts)
    # logger.info(
    #     "Copied {}'s boosts: {}".format(side.active.name, dict(side.active.boosts))
    # )
    #
    # if constants.TRANSFORM not in side.active.volatile_statuses:
    #     side.active.volatile_statuses.append(constants.TRANSFORM)
    #
    # transformed_into = other_side.active
    # side.active.stats = deepcopy(transformed_into.stats)
    # side.active.moves = deepcopy(transformed_into.moves)
    # side.active.types = deepcopy(transformed_into.types)
    # side.active.boosts = deepcopy(transformed_into.boosts)
    #
    # for mv in side.active.moves:
    #     mv.current_pp = 5
    #
    # if split_msg[-1].startswith("[from]") and "ability:" in split_msg[-1]:
    #     side.active.original_ability = normalize_name(
    #         split_msg[-1].split("ability:")[-1].strip()
    #     )
    # elif side.active.ability is not None:
    #     side.active.original_ability = side.active.ability
    #
    # side.active.ability = deepcopy(transformed_into.ability)


def turn(battle, split_msg):
    battle.turn = int(split_msg[2])
    logger.info("")
    logger.info("Turn: {}".format(battle.turn))


def noinit(battle, split_msg):
    if split_msg[2] == "rename":
        battle.battle_tag = split_msg[3]
        logger.info("Renamed battle to {}".format(battle.battle_tag))


def update_speed_range(
    battle, opponent_pkmn: Pokemon, bot_pkmn: Pokemon, other_pkmn_faster_than=True
):
    bot_pkmn = deepcopy(bot_pkmn)

    speed_threshold = int(
        boost_multiplier_lookup[bot_pkmn.boosts[constants.SPEED]]
        * bot_pkmn.stats[constants.SPEED]
        / boost_multiplier_lookup[opponent_pkmn.boosts[constants.SPEED]]
    )

    if opponent_pkmn.ability == "swiftswim" and battle.weather in [
        constants.RAIN,
        constants.HEAVY_RAIN,
    ]:
        speed_threshold = int(speed_threshold / 2)

    if opponent_pkmn.ability == "chlorophyll" and battle.weather in [
        constants.SUN,
        constants.DESOLATE_LAND,
    ]:
        speed_threshold = int(speed_threshold / 2)

    if (
        opponent_pkmn.ability == "slushrush"
        and battle.weather in constants.HAIL_OR_SNOW
    ):
        speed_threshold = int(speed_threshold / 2)

    if opponent_pkmn.ability == "sandrush" and battle.weather == constants.SAND:
        speed_threshold = int(speed_threshold / 2)

    if (
        opponent_pkmn.ability == "surgesurfer"
        and battle.field == constants.ELECTRIC_TERRAIN
    ):
        speed_threshold = int(speed_threshold / 2)

    if opponent_pkmn.ability == "quickfeet" and opponent_pkmn.status is not None:
        speed_threshold = int(speed_threshold / 2)

    if battle.opponent.side_conditions[constants.TAILWIND]:
        speed_threshold = int(speed_threshold / 2)

    if battle.user.side_conditions[constants.TAILWIND]:
        speed_threshold = int(speed_threshold * 2)

    if opponent_pkmn.status == constants.PARALYZED:
        speed_threshold = int(speed_threshold * 2)

    if bot_pkmn.status == constants.PARALYZED:
        speed_threshold = int(speed_threshold / 2)

    if opponent_pkmn.item == "choicescarf":
        speed_threshold = int(speed_threshold / 1.5)

    if bot_pkmn.item == "choicescarf":
        speed_threshold = int(speed_threshold * 1.5)

    if "protosynthesisspe" in opponent_pkmn.volatile_statuses:
        speed_threshold = int(speed_threshold / 1.5)

    if "protosynthesisspe" in bot_pkmn.volatile_statuses:
        speed_threshold = int(speed_threshold * 1.5)

    if "quarkdrivespe" in opponent_pkmn.volatile_statuses:
        speed_threshold = int(speed_threshold / 1.5)

    if "quarkdrivespe" in bot_pkmn.volatile_statuses:
        speed_threshold = int(speed_threshold * 1.5)

    if battle.trick_room:
        other_pkmn_went_first = not other_pkmn_faster_than
    else:
        other_pkmn_went_first = other_pkmn_faster_than

    if other_pkmn_went_first:
        opponent_max_speed = min(opponent_pkmn.speed_range.max, speed_threshold)
        if opponent_max_speed != opponent_pkmn.speed_range.max:
            opponent_pkmn.speed_range = StatRange(
                min=opponent_pkmn.speed_range.min, max=opponent_max_speed
            )
            logger.info(
                "Updated {}'s max speed to {}".format(
                    opponent_pkmn.name, opponent_pkmn.speed_range.max
                )
            )

    else:
        opponent_min_speed = max(opponent_pkmn.speed_range.min, speed_threshold)
        if opponent_min_speed != opponent_pkmn.speed_range.min:
            opponent_pkmn.speed_range = StatRange(
                min=opponent_min_speed, max=opponent_pkmn.speed_range.max
            )
            logger.info(
                "Updated {}'s min speed to {}".format(
                    opponent_pkmn.name, opponent_pkmn.speed_range.min
                )
            )


def check_speed_ranges(battle, msg_lines):
    """
    This function is intended to set the min or max possible speed that the opponent's
    active Pokemon could possibly have given a turn that just happened.

    For example: if both the bot and the opponent use an equal priority move but the
    opponent moves first, then the opponent's min_speed attribute will be set to the
    bots actual speed. This is because the opponent must have at least that much speed
    for it to have gone first.

    These min/max speeds are set without knowledge of items. If the opponent goes first
    when having a choice scarf then min speed will still be set to the bots speed. When
    it comes time to guess a Pokemon's possible set(s), the item must be taken into account
    as well when determining the final speed of a Pokemon. Abilities are NOT taken into
    consideration because their speed modifications are subject to certain conditions
    being present, whereas a choice scarf ALWAYS boosts speed.

    If there is a situation where an ability could have modified the turn order (either by
    changing a move's priority or giving a Pokemon more speed) then this check should be
    skipped. Examples are:
        - either side switched
        - the opponent COULD have a speed-boosting weather ability AND that weather is up
        - the opponent COULD have prankster and it used a status move
        - Grassy Glide is used when Grassy Terrain is up
    """
    for ln in msg_lines:
        # if anyone got `cant` or hit themselves in confusion
        # skip this check as we don't know if they used a priority move
        if ln.startswith("|-activate|") and ln.endswith("confusion"):
            return

        # If anyone used a custapberry, skip this check
        if ln.startswith("|-enditem|") and (
            "custapberry" in normalize_name(ln) or "Custap Berry" in ln
        ):
            return

        # If anyone had quick claw activate, skip this check
        if "quickclaw" in normalize_name(ln) or "Quick Claw" in ln:
            return

        # If anyone had quick claw activate, skip this check
        if "quickdraw" in normalize_name(ln) or "Quick Draw" in ln:
            return

    actionable = [
        m
        for m in msg_lines
        if (m.startswith("|move|") and "[from]" not in m) or m.startswith("|cant|")
    ]

    # replace `cant` with `move` if the bot's side got `cant`
    # only for the bot's side because we know what move we just selected
    for i, m in enumerate(actionable):
        if m.startswith(f"|cant|{battle.user.name}a"):
            if battle.user.slot_a.last_selected_move.turn == battle.turn:
                actionable[i] = (
                    f"|move|{battle.user.name}a: {battle.user.slot_a.active.name}|{battle.user.slot_a.last_selected_move.move}"
                )
                logger.info(
                    f"Replaced cant for {battle.user.slot_a.active.name} with last selected move: {actionable[i]}"
                )
        elif m.startswith(f"|cant|{battle.user.name}b"):
            if battle.user.slot_b.last_selected_move.turn == battle.turn:
                actionable[i] = (
                    f"|move|{battle.user.name}b: {battle.user.slot_b.active.name}|{battle.user.slot_b.last_selected_move.move}"
                )
                logger.info(
                    f"Replaced cant for {battle.user.slot_b.active.name} with last selected move: {actionable[i]}"
                )

    moves = [
        get_move_information(m)
        for m in actionable
        if (m.startswith("|move|") and "[from]" not in m)
    ]

    number_of_moves = len(moves)

    if any(m[1][constants.ID] in ["encore", "grassyglide"] for m in moves):
        return

    is_opp = [m[0].startswith(battle.opponent.name) for m in moves]
    priorities = [
        m[1][constants.PRIORITY] for m in moves if m[1][constants.PRIORITY] is not None
    ]
    ssa = [get_side_slot_active(battle, [None, None, m[0]]) for m in moves]

    for i in range(number_of_moves):
        if is_opp[i]:
            opp_pkmn = ssa[i][3]
            if (
                opp_pkmn is None
                or can_have_speed_modified(opp_pkmn)
                or can_have_priority_modified(
                    battle, opp_pkmn, moves[i][1][constants.ID]
                )
            ):
                continue

            found_bot_pkmn = False
            bot_pkmn = None
            faster_than = i - 1
            while not found_bot_pkmn:
                if faster_than < 0:
                    break
                if (
                    not is_opp[faster_than]
                    and priorities[faster_than] == priorities[i]
                    and not can_have_priority_modified(
                        battle, ssa[faster_than][3], moves[i][1][constants.ID]
                    )
                ):
                    bot_pkmn = ssa[faster_than][3]
                    found_bot_pkmn = True
                faster_than -= 1

            if bot_pkmn is not None:
                update_speed_range(
                    battle, opp_pkmn, bot_pkmn, other_pkmn_faster_than=True
                )

            found_bot_pkmn = False
            bot_pkmn = None
            faster_than = i + 1
            while not found_bot_pkmn:
                if faster_than > number_of_moves - 1:
                    break
                if (
                    not is_opp[faster_than]
                    and priorities[faster_than] == priorities[i]
                    and not can_have_priority_modified(
                        battle, ssa[faster_than][3], moves[i][1][constants.ID]
                    )
                ):
                    bot_pkmn = ssa[faster_than][3]
                    found_bot_pkmn = True
                faster_than += 1

            if bot_pkmn is not None:
                update_speed_range(
                    battle, opp_pkmn, bot_pkmn, other_pkmn_faster_than=False
                )

    bot_side_fainted = [
        (i, m)
        for (i, m) in enumerate(msg_lines)
        if (m.startswith(f"|faint|{battle.user.name}"))
    ]
    for i, faint_msg in bot_side_fainted:
        slot_letter = faint_msg.split("|")[2][2]
        # check for switch or drag on the same slot, if so skip
        if any(
            m
            for m in msg_lines
            if (
                m.startswith(f"|switch|{battle.user.name}{slot_letter}")
                or m.startswith(f"|drag|{battle.user.name}{slot_letter}")
                or m.startswith(f"|move|{battle.user.name}{slot_letter}")
            )
        ):
            continue
        # get last selected move for the slot
        if slot_letter == "a":
            last_move = battle.user.slot_a.last_selected_move
            pkmn = battle.user.slot_a.active
        else:
            last_move = battle.user.slot_b.last_selected_move
            pkmn = battle.user.slot_b.active

        # skip if the last move was a switch or not on this turn
        if (
            last_move.move.startswith("switch")
            or last_move.turn != battle.turn
            or last_move.move not in all_move_json
        ):
            continue

        # if the last selected move was on this turn, we can use it to update speed ranges
        last_move_dict = all_move_json[last_move.move]
        if last_move.turn == battle.turn:
            # find all opponent moves with the same priority that happened before this faint
            moves = [
                get_move_information(m)
                for (ii, m) in enumerate(msg_lines)
                if (m.startswith("|move|") and "[from]" not in m) and ii < i
            ]
            same_priority_moves = [
                m
                for m in moves
                if (
                    not m[0].startswith(battle.user.name)
                    and m[1][constants.PRIORITY] == last_move_dict[constants.PRIORITY]
                )
            ]

            for opp_pkmn, opp_pkmn_used_move in same_priority_moves:
                if not can_have_priority_modified(
                    battle, pkmn, opp_pkmn_used_move[constants.ID]
                ):
                    _, _, _, opp_pkmn = get_side_slot_active(
                        battle, [None, None, opp_pkmn]
                    )
                    logger.info(
                        f"Bot's {pkmn.name} fainted before it could use {last_move.move}, "
                        + f"{opp_pkmn.name} using {opp_pkmn_used_move[constants.NAME]} must be at least as fast"
                    )
                    update_speed_range(
                        battle, opp_pkmn, pkmn, other_pkmn_faster_than=False
                    )


def check_opponent_hiddenpower(battle, msg_line):
    """
    `msg_line` is should be the line *after* |-move|...|Hidden Power|...
    and is meant to be called for the opponent's pkmn only

    This function checks if the move was resisted, super-effective, or neutral.
    It then updates pkmn.hidden_power_possibilities based on that information
    """
    ...
    # attacker = battle.opponent.active
    # defender_types = battle.user.active.types
    # logger.info(
    #     "Checking hiddenpower possibilities for opponent's {}".format(attacker.name)
    # )
    # logger.info(
    #     "Starting hiddenpower possibilities {}".format(
    #         attacker.hidden_power_possibilities
    #     )
    # )
    #
    # next_line_split_msg = msg_line.split("|")
    # if next_line_split_msg[1] == "-resisted":
    #     logger.info("{} resisted hiddenpower".format(defender_types))
    #     for t in list(attacker.hidden_power_possibilities):
    #         if not is_not_very_effective(t, defender_types):
    #             attacker.hidden_power_possibilities.remove(t)
    #
    # elif next_line_split_msg[1] == "-supereffective":
    #     logger.info("{} was weak to hiddenpower".format(defender_types))
    #     for t in list(attacker.hidden_power_possibilities):
    #         if not is_super_effective(t, defender_types):
    #             attacker.hidden_power_possibilities.remove(t)
    #
    # elif next_line_split_msg[1] == "-damage":
    #     logger.info("{} was neutral to hiddenpower".format(defender_types))
    #     for t in list(attacker.hidden_power_possibilities):
    #         if not is_neutral_effectiveness(t, defender_types):
    #             attacker.hidden_power_possibilities.remove(t)
    #
    # else:
    #     logger.info(
    #         "Cannot update hiddenpower possibilities with: {}".format(
    #             next_line_split_msg[1]
    #         )
    #     )
    #     return
    #
    # logger.info(
    #     "Remaining hiddenpower possibilities: {}".format(
    #         attacker.hidden_power_possibilities
    #     )
    # )


def check_choicescarf(battle, msg_lines):
    # If either side switched this turn - don't do this check
    ...
    # if any(
    #     battle.generation in ["gen1", "gen2", "gen3"]
    #     or ln.startswith("|switch|")
    #     or ln.startswith("|cant|")
    #     or (ln.startswith("|-activate|") and ln.endswith("confusion"))
    #     for ln in msg_lines
    # ) or battle.user.last_selected_move.move.startswith("switch "):
    #     return
    #
    # moves = [get_move_information(m) for m in msg_lines if m.startswith("|move|")]
    # number_of_moves = len(moves)
    #
    # # if the bot went first we cannot ever infer a choicescarf
    # if number_of_moves not in [1, 2] or moves[0][0].startswith(battle.user.name):
    #     return
    #
    # elif number_of_moves == 1:
    #     moves.append(
    #         (
    #             "{}a: {}".format(battle.opponent.name, battle.user.active.name),
    #             all_move_json[normalize_name(battle.user.last_selected_move.move)],
    #         )
    #     )
    #
    # if moves[0][1][constants.PRIORITY] != moves[1][1][constants.PRIORITY]:
    #     return
    #
    # battle_copy = deepcopy(battle)
    # if (
    #     battle.opponent.active is None
    #     or battle.opponent.active.item != constants.UNKNOWN_ITEM
    #     or not battle.opponent.active.can_have_choice_item
    #     or can_have_speed_modified(battle, battle.opponent.active)
    #     or can_have_priority_modified(
    #         battle, battle.opponent.active, moves[0][1][constants.ID]
    #     )
    #     or can_have_priority_modified(
    #         battle, battle.user.active, moves[1][1][constants.ID]
    #     )
    #     or (
    #         battle_copy.user.active.ability == "unburden"
    #         and battle_copy.user.active.item is None
    #     )
    # ):
    #     return
    #
    # if battle.battle_type == constants.RANDOM_BATTLE:
    #     battle_copy.opponent.active.set_spread(
    #         "serious", "85,85,85,85,85,85"
    #     )  # random battles have known spreads
    # else:
    #     if battle.trick_room:
    #         battle_copy.opponent.active.set_spread(
    #             "quiet", "0,0,0,0,0,0"
    #         )  # assume as slow as possible in trickroom
    #     else:
    #         battle_copy.opponent.active.set_spread(
    #             "jolly", "0,0,0,0,0,252"
    #         )  # assume as fast as possible
    # opponent_effective_speed = battle_copy.get_effective_speed(battle_copy.opponent)
    # bot_effective_speed = battle_copy.get_effective_speed(battle_copy.user)
    #
    # if battle.trick_room:
    #     has_scarf = opponent_effective_speed > bot_effective_speed
    # else:
    #     has_scarf = bot_effective_speed > opponent_effective_speed
    #
    # if has_scarf:
    #     logger.info(
    #         "Opponent {} could not have gone first - setting it's item to choicescarf".format(
    #             battle.opponent.active.name
    #         )
    #     )
    #     battle.opponent.active.item = "choicescarf"
    #     battle.opponent.active.item_inferred = True


def get_single_damage_dealt(
    battle: Battle,
    potential_damage_dealt: DamageDealt,
    need_to_find: str,
    next_messages: list[str],
) -> DamageDealt | None:
    for line in next_messages:
        next_line_split = line.split("|")
        # if one of these strings appears in index 1 then
        # exit out since we are done with this pokemon's move
        if next_line_split[1] == "-miss" and next_line_split[3].startswith(
            need_to_find
        ):
            break
        if len(next_line_split) < 2 or next_line_split[1] in MOVE_END_STRINGS:
            break

        elif next_line_split[1] == "-crit" and need_to_find in next_line_split[2]:
            potential_damage_dealt.crit = True

        # if '-damage' appears, we want to parse the percentage damage dealt
        # but only if the target was the other side (i.e. don't do this for friendly fire)
        elif next_line_split[1] == "-damage" and need_to_find in next_line_split[2]:
            other_side, attacking_side, target_slot, target = get_side_slot_active(
                battle, next_line_split
            )
            final_health, maxhp, _ = get_pokemon_info_from_condition(next_line_split[3])
            # maxhp can be 0 if the targetted pokemon fainted
            # the message would be: "0 fnt"
            if maxhp == 0:
                maxhp = target.max_hp

            damage_dealt = (target.hp / target.max_hp) * maxhp - final_health
            damage_percentage = round(damage_dealt / maxhp, 4)

            logger.info(
                "{} did {}% damage to {} with {}".format(
                    potential_damage_dealt.attacker_slot.active.name,
                    damage_percentage * 100,
                    target.name,
                    potential_damage_dealt.move,
                )
            )
            potential_damage_dealt.percent_damage = damage_percentage
            potential_damage_dealt.target_slot = target_slot
            return potential_damage_dealt


def get_damage_dealt(battle, split_msg, next_messages) -> list[DamageDealt | None]:
    move_name = normalize_name(split_msg[3])

    attacking_side, other_side, attacking_slot, attacking_pkmn = get_side_slot_active(
        battle, split_msg
    )

    spread_line = [msg for msg in split_msg if msg.startswith("[spread]")]
    if len(spread_line) == 1:
        spread = True
        need_to_find = spread_line[0].split(" ")[1].split(",")
    elif len(spread_line) == 0:
        spread = False
        need_to_find = [split_msg[4].split(":")[0]]
    else:
        raise ValueError(
            "Spread line should be 0 or 1, got {}: {}".format(
                len(spread_line), split_msg
            )
        )

    result = []
    for ntf in need_to_find:
        # don't get damage dealt to the attacking side
        if ntf.startswith(attacking_side.name):
            continue
        damage_dealt = get_single_damage_dealt(
            battle,
            DamageDealt(
                attacker_side=deepcopy(attacking_side),
                attacker_slot=deepcopy(attacking_slot),
                target_side=deepcopy(other_side),
                target_slot=None,  # will be set later
                move=move_name,
                percent_damage=None,  # will be set later
                crit=False,  # may be set later
                spread=spread,
            ),
            ntf,
            next_messages,
        )
        if damage_dealt is not None:
            result.append(damage_dealt)

    return result


def _do_check(
    battle_copy,
    opponent_slot,
    possibilites,
    check_type,
    damage_dealt,
    bot_went_first,
    check_lower_bound,
    allow_emptying=False,
):
    actual_damage_dealt = (
        damage_dealt.percent_damage * damage_dealt.target_slot.active.max_hp
    )

    indicies_to_remove = []
    num_starting_possibilites = len(possibilites)
    for i in range(num_starting_possibilites):
        p = possibilites[i]

        if opponent_slot.identifier == "a":
            battle_copy.opponent.slot_a.active.set_spread(
                p.nature, ",".join(str(x) for x in p.evs)
            )
        else:
            battle_copy.opponent.slot_b.active.set_spread(
                p.nature, ",".join(str(x) for x in p.evs)
            )

        if check_type == "damage_received":
            if opponent_slot.identifier == "a":
                actual_damage_dealt = (
                    damage_dealt.percent_damage
                    * battle_copy.opponent.slot_a.active.max_hp
                )
            else:
                actual_damage_dealt = (
                    damage_dealt.percent_damage
                    * battle_copy.opponent.slot_b.active.max_hp
                )

            if bot_went_first:
                opponent_move = constants.DO_NOTHING_MOVE
            else:
                opponent_move = opponent_slot.last_used_move.move

            damage = poke_engine_get_damage_rolls(
                battle_copy,
                damage_dealt.attacker_side.identifier,
                damage_dealt.attacker_slot.identifier,
                damage_dealt.target_side.identifier,
                damage_dealt.target_slot.identifier,
                damage_dealt.move,
                opponent_move,
            )
        elif check_type == "damage_dealt":
            damage = poke_engine_get_damage_rolls(
                battle_copy,
                damage_dealt.attacker_side.identifier,
                damage_dealt.attacker_slot.identifier,
                damage_dealt.target_side.identifier,
                damage_dealt.target_slot.identifier,
                damage_dealt.move,
                damage_dealt.target_slot.last_selected_move.move,
            )
        else:
            raise ValueError("Invalid check_type: {}".format(check_type))

        if damage_dealt.crit:
            max_damage = damage[1]
        else:
            max_damage = damage[0]

        damage = [max_damage * 0.85, max_damage]
        lower_bound_violated = check_lower_bound and (
            actual_damage_dealt < (damage[0] * 0.975 - 2.5)
        )
        upper_bound_violated = actual_damage_dealt > (damage[1] * 1.025 + 2.5)
        if lower_bound_violated or upper_bound_violated:
            logger.debug(
                "{} is invalid based on reverse damage calc. damage_dealt={}, lower={}, upper={}".format(
                    p, actual_damage_dealt, damage[0], damage[1]
                )
            )
            indicies_to_remove.append(i)

    if len(indicies_to_remove) == num_starting_possibilites and not allow_emptying:
        logger.warning("Would remove all possibilities, not removing any")
        logger.warning(f"{actual_damage_dealt=}")
        return

    for i in reversed(indicies_to_remove):
        possibilites.pop(i)


def update_dataset_possibilities(
    battle: Battle,
    damage_dealt: DamageDealt,
    check_type: str,
):
    if (
        # battle.wait
        damage_dealt.attacker_slot.active is None
        or damage_dealt.target_slot.active is None
        or damage_dealt.attacker_slot.active.hp <= 0
        or damage_dealt.target_slot.active.hp <= 0
        or damage_dealt.attacker_slot.active.name
        in ["ditto", "shedinja", "terapagosterastal", "meloetta", "meloettapirouette"]
        or damage_dealt.target_slot.active.name
        in ["ditto", "shedinja", "terapagosterastal", "meloetta", "meloettapirouette"]
        or damage_dealt.move not in all_move_json
        or all_move_json[damage_dealt.move][constants.CATEGORY] == constants.STATUS
        or "multiaccuracy" in all_move_json[damage_dealt.move]
        or damage_dealt.move.startswith(constants.HIDDEN_POWER)
        or damage_dealt.percent_damage <= 0.02
        or (
            check_type == "damage_dealt"
            and damage_dealt.move
            not in [
                battle.opponent.slot_a.last_used_move.move,
                battle.opponent.slot_b.last_used_move.move,
            ]
        )
        or (
            check_type == "damage_received"
            and damage_dealt.move
            not in [
                battle.user.slot_a.last_used_move.move,
                battle.user.slot_b.last_used_move.move,
            ]
        )
        or damage_dealt.move
        in [
            "pursuit",
            "struggle",
            "counter",
            "mirrorcoat",
            "metalburst",
            "foulplay",
            "ficklebeam",
            "lashout",
            "ragefist",
            "shellsidearm",
            "futuresight",
        ]
    ):
        return

    battle_copy = deepcopy(battle)
    check_lower_bound = True
    if check_type == "damage_dealt":
        opponent_slot = damage_dealt.attacker_slot
        smogon_possibilities = SmogonSets.get_pokemon_from_sets(
            opponent_slot.active.name
        )
        user_percent_hp = round(
            damage_dealt.target_slot.active.hp / damage_dealt.target_slot.active.max_hp,
            2,
        )
        if abs(damage_dealt.percent_damage - user_percent_hp) < 0.02:
            check_lower_bound = False
        bot_went_first = (
            damage_dealt.attacker_slot.last_used_move.turn
            == damage_dealt.target_slot.last_used_move.turn
        )
    elif check_type == "damage_received":
        opponent_slot = damage_dealt.target_slot
        smogon_possibilities = SmogonSets.get_pokemon_from_sets(
            damage_dealt.target_slot.active.name
        )
        opponent_percent_hp = round(
            opponent_slot.active.hp / opponent_slot.active.max_hp, 2
        )
        if abs(damage_dealt.percent_damage - opponent_percent_hp) < 0.02:
            check_lower_bound = False
        bot_went_first = (
            damage_dealt.target_slot.last_used_move.turn
            != damage_dealt.attacker_slot.last_used_move.turn
        )
    else:
        raise ValueError("Invalid check_type: {}".format(check_type))

    logger.debug(f"{check_type=}")
    logger.debug(f"{check_lower_bound=}")
    logger.debug(f"{bot_went_first=}")

    if smogon_possibilities is None:
        logger.info("Skipping dataset check because no SmogonSets found")
        return

    _do_check(
        battle_copy,
        opponent_slot,
        smogon_possibilities,
        check_type,
        damage_dealt,
        bot_went_first,
        check_lower_bound,
        allow_emptying=False,  # never completely empty smogon stats
    )


def check_heavydutyboots(battle, msg_lines):
    ...
    # side_to_check = battle.opponent
    #
    # if (
    #     battle.generation not in ["gen8", "gen9"]
    #     or side_to_check.active.item != constants.UNKNOWN_ITEM
    #     or "magicguard"
    #     in [
    #         normalize_name(a)
    #         for a in pokedex[side_to_check.active.name][constants.ABILITIES].values()
    #     ]
    # ):
    #     return
    #
    # if side_to_check.side_conditions[constants.STEALTH_ROCK] > 0:
    #     pkmn_took_stealthrock_damage = False
    #     for line in msg_lines:
    #         split_line = line.split("|")
    #
    #         # |-damage|p2a: Weedle|88/100|[from] Stealth Rock
    #         if (
    #             len(split_line) > 4
    #             and split_line[1] == "-damage"
    #             and split_line[2].startswith(side_to_check.name)
    #             and split_line[4] == "[from] Stealth Rock"
    #         ):
    #             pkmn_took_stealthrock_damage = True
    #
    #     if not pkmn_took_stealthrock_damage:
    #         logger.info("{} has heavydutyboots".format(side_to_check.active.name))
    #         side_to_check.active.item = "heavydutyboots"
    #         side_to_check.active.item_inferred = True
    #     else:
    #         logger.info(
    #             "{} was affected by stealthrock, it cannot have heavydutyboots".format(
    #                 side_to_check.active.name
    #             )
    #         )
    #         side_to_check.active.impossible_items.add(constants.HEAVY_DUTY_BOOTS)
    #
    # elif (
    #     side_to_check.side_conditions[constants.SPIKES] > 0
    #     and "levitate"
    #     not in [
    #         normalize_name(a)
    #         for a in pokedex[side_to_check.active.name][constants.ABILITIES].values()
    #     ]
    #     and not side_to_check.active.has_type("flying")
    #     and side_to_check.active.ability != "levitate"
    # ):
    #     pkmn_took_spikes_damage = False
    #     for line in msg_lines:
    #         split_line = line.split("|")
    #
    #         # |-damage|p2a: Weedle|88/100|[from] Spikes
    #         if (
    #             len(split_line) > 4
    #             and split_line[1] == "-damage"
    #             and split_line[2].startswith(side_to_check.name)
    #             and split_line[4] == "[from] Spikes"
    #         ):
    #             pkmn_took_spikes_damage = True
    #
    #     if not pkmn_took_spikes_damage:
    #         logger.info("{} has heavydutyboots".format(side_to_check.active.name))
    #         side_to_check.active.item = "heavydutyboots"
    #         side_to_check.active.item_inferred = True
    #     else:
    #         logger.info(
    #             "{} was affected by spikes, it cannot have heavydutyboots".format(
    #                 side_to_check.active.name
    #             )
    #         )
    #         side_to_check.active.impossible_items.add(constants.HEAVY_DUTY_BOOTS)
    # elif (
    #     side_to_check.side_conditions[constants.TOXIC_SPIKES] > 0
    #     and side_to_check.active.status is None
    #     and not side_to_check.active.has_type("flying")
    #     and not side_to_check.active.has_type("poison")
    #     and not side_to_check.active.has_type("steel")
    #     and side_to_check.active.ability != "levitate"
    #     and "levitate"
    #     not in [
    #         normalize_name(a)
    #         for a in pokedex[side_to_check.active.name][constants.ABILITIES].values()
    #     ]
    #     and side_to_check.active.ability not in constants.IMMUNE_TO_POISON_ABILITIES
    # ):
    #     pkmn_took_toxicspikes_poison = False
    #     for line in msg_lines:
    #         split_line = line.split("|")
    #
    #         # a pokemon can be toxic-ed from sources other than toxicspikes
    #         # stopping at one of these strings ensures those other sources aren't considered
    #         if len(split_line) < 2 or split_line[1] in {"move", "upkeep", ""}:
    #             break
    #
    #         # |-status|p2a: Pikachu|psn
    #         if (
    #             split_line[1] == "-status"
    #             and (
    #                 split_line[3] == constants.POISON
    #                 or split_line[3] == constants.TOXIC
    #             )
    #             and split_line[2].startswith(side_to_check.name)
    #         ):
    #             pkmn_took_toxicspikes_poison = True
    #
    #     if not pkmn_took_toxicspikes_poison:
    #         logger.info("{} has heavydutyboots".format(side_to_check.active.name))
    #         side_to_check.active.item = "heavydutyboots"
    #         side_to_check.active.item_inferred = True
    #     else:
    #         logger.info(
    #             "{} was affected by toxicspikes, it cannot have heavydutyboots".format(
    #                 side_to_check.active.name
    #             )
    #         )
    #         side_to_check.active.impossible_items.add(constants.HEAVY_DUTY_BOOTS)
    #
    # elif (
    #     side_to_check.side_conditions[constants.STICKY_WEB] > 0
    #     and not side_to_check.active.has_type("flying")
    #     and "levitate"
    #     not in [
    #         normalize_name(a)
    #         for a in pokedex[side_to_check.active.name][constants.ABILITIES].values()
    #     ]
    # ):
    #     pkmn_was_affected_by_stickyweb = False
    #     for line in msg_lines:
    #         split_line = line.split("|")
    #
    #         # |-activate|p2a: Gengar|move: Sticky Web
    #         if (
    #             len(split_line) == 4
    #             and split_line[1] == "-activate"
    #             and split_line[2].startswith(side_to_check.name)
    #             and split_line[3] == "move: Sticky Web"
    #         ):
    #             pkmn_was_affected_by_stickyweb = True
    #
    #     if not pkmn_was_affected_by_stickyweb:
    #         logger.info("{} has heavydutyboots".format(side_to_check.active.name))
    #         side_to_check.active.item = "heavydutyboots"
    #         side_to_check.active.item_inferred = True
    #     else:
    #         logger.debug(
    #             "{} was affected by sticky web, it cannot have heavydutyboots".format(
    #                 side_to_check.active.name
    #             )
    #         )
    #         side_to_check.active.impossible_items.add(constants.HEAVY_DUTY_BOOTS)


def update_battle(battle: Battle, msg: str):
    msg_lines = msg.split("\n")
    for line in msg_lines:
        split_msg = line.split("|")
        if len(split_msg) < 2:
            continue

        action = split_msg[1].strip()
        if action == "request":
            request(battle, split_msg)
            process_battle_updates(battle)
            return not battle.wait
        else:
            battle.msg_list.append(line)

    return False


def get_next_speed_range_end(battle, msg_list):
    # finds the first spot in msg_list that an effective speed could have changed
    # this is used to know which subset of msg_list can be fed into check_speed_ranges
    active_pkmn = [
        battle.user.slot_a.active,
        battle.user.slot_b.active,
        battle.opponent.slot_a.active,
        battle.opponent.slot_b.active,
    ]
    active_pkmn = [p for p in active_pkmn if p is not None]
    i = 0
    for i, line in enumerate(msg_list):
        split_msg = line.split("|")
        if len(split_msg) < 4:
            continue

        # tailwind activates for either side
        if split_msg[1] == "-sidestart" and split_msg[3] == "move: Tailwind":
            return i
        elif (
            split_msg[1] == "-weather"
            and normalize_name(split_msg[2]) in [constants.RAIN, constants.HEAVY_RAIN]
            and any(p.ability == "swiftswim" for p in active_pkmn)
        ):
            return i
        elif (
            split_msg[1] == "-weather"
            and normalize_name(split_msg[2]) == constants.SAND
            and any(p.ability == "sandrush" for p in active_pkmn)
        ):
            return i
        elif (
            split_msg[1] == "-weather"
            and normalize_name(split_msg[2]) in constants.HAIL_OR_SNOW
            and any(p.ability == "slushrush" for p in active_pkmn)
        ):
            return i
        elif (
            split_msg[1] == "-weather"
            and normalize_name(split_msg[2]) in [constants.SUN, constants.DESOLATE_LAND]
            and any(p.ability == "chlorophyll" for p in active_pkmn)
        ):
            return i

    return i + 1


def process_battle_updates(battle: Battle):
    msg_lines = battle.msg_list
    next_speed_range_check = -1
    for i, line in enumerate(msg_lines):
        if i > next_speed_range_check:
            next_speed_range_check = get_next_speed_range_end(battle, msg_lines[i:])
            check_speed_ranges(battle, msg_lines[i : i + next_speed_range_check])

        split_msg = line.split("|")
        if len(split_msg) < 2:
            continue

        action = split_msg[1].strip()

        battle_modifiers_lookup = {
            "switch": switch,
            "faint": faint,
            "-fail": fail,
            "drag": drag,
            "-heal": heal_or_damage,
            "-damage": heal_or_damage,
            "-sethp": sethp,
            "move": move,
            "-setboost": setboost,
            "-boost": boost,
            "-unboost": unboost,
            "-status": status,
            "-activate": activate,
            "-anim": anim,
            "-prepare": prepare,
            "-start": start_volatile_status,
            "-singlemove": start_volatile_status,
            "-end": end_volatile_status,
            "-curestatus": curestatus,
            "-cureteam": cureteam,
            "-weather": weather,
            "-fieldstart": fieldstart,
            "-fieldend": fieldend,
            "-sidestart": sidestart,
            "-sideend": sideend,
            "-swapsideconditions": swapsideconditions,
            "-item": set_item,
            "-enditem": remove_item,
            "-immune": immune,
            "-ability": update_ability,
            "detailschange": form_change,
            "replace": illusion_end,
            "-formechange": form_change,
            "-transform": transform,
            "-mega": mega,
            "-terastallize": terastallize,
            "-zpower": zpower,
            "-clearnegativeboost": clearnegativeboost,
            "-clearboost": clearboost,
            "-clearallboost": clearallboost,
            "-singleturn": singleturn,
            "-mustrecharge": mustrecharge,
            "upkeep": upkeep,
            "cant": cant,
            "inactive": inactive,
            "inactiveoff": inactiveoff,
            "turn": turn,
            "noinit": noinit,
        }

        function_to_call = battle_modifiers_lookup.get(action)
        if function_to_call is not None:
            function_to_call(battle, split_msg)

        if action == "move" and is_opponent(battle, split_msg):
            damage_dealt = get_damage_dealt(battle, split_msg, msg_lines[i + 1 :])
            for dd in damage_dealt:
                update_dataset_possibilities(battle, dd, "damage_dealt")

            if is_slot_a(split_msg):
                attacking_slot = battle.opponent.slot_a
            else:
                attacking_slot = battle.opponent.slot_b
            for dd in damage_dealt:
                check_stellar_boost(attacking_slot, dd)

        elif action == "move" and not is_opponent(battle, split_msg):
            damage_dealt = get_damage_dealt(battle, split_msg, msg_lines[i + 1 :])
            for dd in damage_dealt:
                update_dataset_possibilities(battle, dd, "damage_received")

            if is_slot_a(split_msg):
                attacking_slot = battle.user.slot_a
            else:
                attacking_slot = battle.user.slot_b
            for dd in damage_dealt:
                check_stellar_boost(attacking_slot, dd)

    battle.msg_list.clear()


async def async_update_battle(battle, msg):
    return update_battle(battle, msg)
