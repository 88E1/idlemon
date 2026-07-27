import logging

import constants
from data import all_move_json
from fp.helpers import normalize_name

logger = logging.getLogger(__name__)


def _find_reserve_for_switch(battle, switch_pokemon: str):
    target = normalize_name(switch_pokemon)
    for pkmn in battle.user.reserve:
        if not pkmn.name or pkmn.name == "none" or pkmn.hp <= 0 or pkmn.fainted:
            continue
        if normalize_name(pkmn.name) == target:
            return pkmn
        if normalize_name(getattr(pkmn, "base_name", "")) == target:
            return pkmn
    return None


def format_decision(battle, slot, decision):
    # Formats a decision for communication with Pokemon-Showdown
    # If the pokemon can mega-evolve, it will
    # If the move can be used as a Z-Move, it will be

    if decision.startswith(constants.SWITCH_STRING + " "):
        switch_pokemon = decision.split("switch ", 1)[-1].strip()
        pkmn = _find_reserve_for_switch(battle, switch_pokemon)
        if pkmn is None:
            reserve_debug = [(p.name, p.index, p.hp) for p in battle.user.reserve]
            raise ValueError(
                "Tried to switch to: {} (reserve={})".format(
                    switch_pokemon, reserve_debug
                )
            )
        message = "switch {}".format(pkmn.index)
    elif decision.lower().startswith("no move"):
        return "pass"
    else:
        tera = False
        if decision.endswith(",tera"):
            decision = decision.removesuffix(",tera")
            tera = True

        decision_split = decision.split(",")
        decision = decision_split[0]
        if len(decision_split) == 3:
            if decision_split[2] == "a":
                target = 1
            elif decision_split[2] == "b":
                target = 2
            else:
                raise ValueError("Invalid slot target: {}".format(decision_split[2]))
            if decision_split[1] == "1":
                target *= -1
            elif decision_split[1] == "2":
                target *= 1
            else:
                raise ValueError("Invalid side target: {}".format(decision_split[1]))

            if (
                all_move_json[decision].get("flags", {}).get("charge")
                and decision in slot.active.volatile_statuses
            ):
                logger.info("Skipping target because {} was charging".format(decision))
                decision = "1"
            elif decision == "terastarstorm" and slot.active.terastallized:
                logger.info(
                    "Skipping target because terastarstorm is being used while terastallized".format()
                )
            elif decision == "outrage" and len(slot.active.moves) != 1:
                logger.info(
                    "Skipping target because outrage is a random target".format()
                )
            else:
                decision = f"{decision} {target}"

        # recharge always needs a target
        if decision == "recharge":
            decision = "recharge 1"

        message = "move {}".format(decision)
        if slot.active.can_mega_evo:
            message = "{} {}".format(message, constants.MEGA)
        elif slot.active.can_ultra_burst:
            message = "{} {}".format(message, constants.ULTRA_BURST)

        # only dynamax on last pokemon
        # if slot.active.can_dynamax and all(p.hp == 0 for p in battle.user.reserve):
        #     message = "{} {}".format(message, constants.DYNAMAX)

        if tera:
            message = "{} {}".format(message, constants.TERASTALLIZE)

        # if slot.active.get_move(decision).can_z:
        #     message = "{} {}".format(message, constants.ZMOVE)

    return message
