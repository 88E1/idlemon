"""Serialize battle state + legal action whitelists for LLM move selection."""

from __future__ import annotations

import logging

import constants
from data import all_move_json
from fp.helpers import (
    is_replacement_request,
    normalize_name,
    type_effectiveness_modifier,
)
from fp.vgc_intel import (
    BASE_META_HINTS,
    build_damage_ko_matrix,
    build_incoming_ko_matrix,
    build_opponent_inferences,
    build_priority_threats,
    build_protect_status,
    build_team_roles,
    build_turn_plan_hints,
    contextual_meta_hints,
    recommend_team_preview,
)

logger = logging.getLogger(__name__)

# Targets that do not need a slot specifier in format_decision
_NO_TARGET = {
    "self",
    "allAdjacentFoes",
    "allAdjacent",
    "all",
    "allySide",
    "foeSide",
    "allyTeam",
    "allies",
    "scripted",
    "randomNormal",
}

# Type-based defensive abilities that nullify or absorb attacks.
_TYPE_IMMUNITY_ABILITIES = {
    "levitate": {"ground"},
    "eartheater": {"ground"},
    "flashfire": {"fire"},
    "wellbakedbody": {"fire"},
    "waterabsorb": {"water"},
    "dryskin": {"water"},
    "stormdrain": {"water"},
    "voltabsorb": {"electric"},
    "lightningrod": {"electric"},
    "motordrive": {"electric"},
    "sapsipper": {"grass"},
}

_META_HINTS = list(BASE_META_HINTS)


def _hp_frac(pkmn) -> float | None:
    if pkmn is None or not pkmn.max_hp:
        return None
    return round(pkmn.hp / pkmn.max_hp, 3)


def _serialize_pkmn(pkmn, *, include_moves: bool = True) -> dict | None:
    if pkmn is None or not pkmn.name or pkmn.name == "none":
        return None
    boosts = {k: v for k, v in dict(pkmn.boosts).items() if v}
    data = {
        "name": pkmn.name,
        "base_name": getattr(pkmn, "base_name", pkmn.name),
        "index": getattr(pkmn, "index", None),
        "hp_frac": _hp_frac(pkmn),
        "hp": pkmn.hp,
        "max_hp": pkmn.max_hp,
        "status": pkmn.status,
        "types": list(pkmn.types) if pkmn.types else [],
        "item": pkmn.item,
        "ability": pkmn.ability,
        "boosts": boosts,
        "volatile_statuses": list(pkmn.volatile_statuses or []),
        "terastallized": bool(pkmn.terastallized),
        "tera_type": pkmn.tera_type,
        "can_mega_evo": bool(getattr(pkmn, "can_mega_evo", False)),
        "can_terastallize": bool(getattr(pkmn, "can_terastallize", False)),
        "fainted": bool(pkmn.hp <= 0 or pkmn.fainted),
    }
    if include_moves:
        data["moves"] = [
            {
                "id": m.name,
                "pp": getattr(m, "current_pp", None),
                "disabled": bool(m.disabled),
                "target": all_move_json.get(normalize_name(m.name), {}).get(
                    "target", "normal"
                ),
            }
            for m in pkmn.moves
        ]
    return data


def _side_conditions(battler) -> dict:
    return {k: v for k, v in dict(battler.side_conditions).items() if v}


def _switch_targets(battle, slot_index: int, already_chosen: set[str]) -> list[str]:
    slot = battle.user.slot_a if slot_index == 0 else battle.user.slot_b
    if getattr(slot, "trapped", False):
        return []

    on_field = set()
    for s in (battle.user.slot_a, battle.user.slot_b):
        active = s.active
        if (
            active
            and active.name
            and active.name != "none"
            and active.hp > 0
            and not active.fainted
        ):
            on_field.add(normalize_name(active.name))
            on_field.add(normalize_name(getattr(active, "base_name", active.name)))

    actions = []
    for p in battle.user.reserve:
        if not p.name or p.name == "none" or p.hp <= 0 or p.fainted:
            continue
        key = normalize_name(p.name)
        base_key = normalize_name(getattr(p, "base_name", None) or p.name)
        if (
            key in on_field
            or base_key in on_field
            or key in already_chosen
            or base_key in already_chosen
        ):
            continue
        actions.append(f"{constants.SWITCH_STRING} {p.name}")
    return actions


def _move_actions_for_active(active, battle, force_switch: bool) -> list[str]:
    if force_switch or active is None or not active.name or active.name == "none":
        return []
    if active.hp <= 0 or active.fainted:
        return []
    if active.status in ("slp", "frz"):
        return ["no move"]

    actions: list[str] = []
    can_tera = bool(getattr(active, "can_terastallize", False))

    def _add(action: str):
        actions.append(action)
        if can_tera and not action.endswith(",tera") and action != "no move":
            actions.append(f"{action},tera")

    for move in active.moves:
        if move.disabled:
            continue
        info = all_move_json.get(normalize_name(move.name), {})
        target = info.get("target", "normal")
        if target in _NO_TARGET:
            _add(move.name)
            continue
        if target in ("adjacentAlly", "adjacentAllyOrSelf"):
            # Partner is the other user slot
            for label in ("1,a", "1,b"):
                # Prefer targeting the ally slot that is not self — both listed;
                # format_decision will send them. Partner index is fine.
                _add(f"{move.name},{label}")
            continue
        if target in ("normal", "any", "adjacentFoe"):
            for label in ("2,a", "2,b"):
                _add(f"{move.name},{label}")
            continue
        # Fallback: untargeted
        _add(move.name)

    if not actions:
        actions.append("no move")
    return actions


def legal_actions_for_slot(
    battle, slot_index: int, already_chosen_switches: set[str] | None = None
) -> list[str]:
    """Return whitelist of internal action strings for one doubles slot."""
    already_chosen_switches = already_chosen_switches or set()
    force_switch = bool(battle.force_switch[slot_index])
    slot = battle.user.slot_a if slot_index == 0 else battle.user.slot_b
    active = slot.active

    # End-of-turn faint replacement: only the fainted slot(s) switch; others pass.
    if is_replacement_request(battle) and not force_switch:
        return ["no move"]

    switches = _switch_targets(battle, slot_index, already_chosen_switches)
    if force_switch or (active and (active.hp <= 0 or active.fainted)):
        return switches or ["no move"]

    moves = _move_actions_for_active(active, battle, force_switch=False)
    # Voluntary switches allowed when not trapped / not force-switch
    return moves + switches


def _alive_active(pkmn) -> bool:
    return bool(
        pkmn
        and pkmn.name
        and pkmn.name != "none"
        and pkmn.hp > 0
        and not pkmn.fainted
    )


def _defending_types(pkmn) -> list[str]:
    if pkmn.terastallized and pkmn.tera_type:
        return [normalize_name(pkmn.tera_type)]
    return [normalize_name(t) for t in (pkmn.types or [])]


def _ability_blocks_type(ability: str | None, move_type: str) -> str | None:
    if not ability or not move_type:
        return None
    blocked = _TYPE_IMMUNITY_ABILITIES.get(normalize_name(ability))
    if blocked and normalize_name(move_type) in blocked:
        return normalize_name(ability)
    return None


def _effective_speed_for_pkmn(battle, battler, pkmn) -> tuple[float, list[str]]:
    """Return (effective_speed, notes) for one active Pokemon in doubles."""
    notes: list[str] = []
    boosted = pkmn.calculate_boosted_stats()[constants.SPEED]
    speed = float(boosted)
    ability = normalize_name(pkmn.ability) if pkmn.ability else None
    item = normalize_name(pkmn.item) if pkmn.item else None
    weather = battle.weather
    field = battle.field
    abilities_suppressed = bool(
        getattr(battle, "neutralizing_gas_is_active", lambda: False)()
    )

    if not abilities_suppressed and ability:
        if weather == constants.SUN and ability == "chlorophyll":
            speed *= 2
            notes.append("Chlorophyll (sun)")
        elif weather == constants.RAIN and ability == "swiftswim":
            speed *= 2
            notes.append("Swift Swim (rain)")
        elif weather == constants.SAND and ability == "sandrush":
            speed *= 2
            notes.append("Sand Rush")
        elif weather in constants.HAIL_OR_SNOW and ability == "slushrush":
            speed *= 2
            notes.append("Slush Rush")
        elif field == constants.ELECTRIC_TERRAIN and ability == "surgesurfer":
            speed *= 2
            notes.append("Surge Surfer")
        elif ability == "unburden" and (
            "unburden" in (pkmn.volatile_statuses or [])
            or not pkmn.item
            or pkmn.item in (None, "", "none")
        ):
            speed *= 2
            notes.append("Unburden")
        elif ability == "quickfeet" and pkmn.status is not None:
            speed *= 1.5
            notes.append("Quick Feet")

    if battler.side_conditions.get(constants.TAILWIND):
        speed *= 2
        notes.append("Tailwind")

    if item == "choicescarf":
        speed *= 1.5
        notes.append("Choice Scarf")

    if (
        pkmn.status == constants.PARALYZED
        and ability != "quickfeet"
        and not abilities_suppressed
    ):
        speed *= 0.5
        notes.append("Paralysis")

    if any(
        vs in (pkmn.volatile_statuses or [])
        for vs in ("quarkdrivespe", "protosynthesisspe")
    ):
        speed *= 1.5
        notes.append("Speed boost (Quark/Proto)")

    # Opponent speeds are often inferred; expose range when known.
    speed_range = getattr(pkmn, "speed_range", None)
    if speed_range is not None:
        lo = getattr(speed_range, "min", 0) or 0
        hi = getattr(speed_range, "max", float("inf"))
        if lo > 0 and (hi == float("inf") or hi > lo):
            # Prefer observed floor when we only know they outsped someone.
            if lo > boosted:
                notes.append(f"speed_floor>={int(lo)}")
        if hi != float("inf") and hi < boosted * 3:
            notes.append(f"speed_cap<={int(hi)}")

    return round(speed, 1), notes


def build_active_speed_order(battle) -> list[dict]:
    """Sorted fastest-first effective speeds for living actives."""
    entries = []
    for side_name, battler in (("user", battle.user), ("opponent", battle.opponent)):
        for slot_label, slot in (("a", battler.slot_a), ("b", battler.slot_b)):
            pkmn = slot.active
            if not _alive_active(pkmn):
                continue
            speed, notes = _effective_speed_for_pkmn(battle, battler, pkmn)
            entries.append(
                {
                    "side": side_name,
                    "slot": slot_label,
                    "name": pkmn.name,
                    "current_speed": speed,
                    "notes": notes,
                }
            )
    reverse = bool(battle.trick_room)
    entries.sort(key=lambda e: e["current_speed"], reverse=not reverse)
    if reverse:
        for e in entries:
            e["notes"] = list(e["notes"]) + ["Trick Room (slowest first)"]
    return entries


def _move_vs_defender(
    move_name: str, defender, abilities_suppressed: bool
) -> dict:
    info = all_move_json.get(normalize_name(move_name), {})
    move_type = normalize_name(info.get("type", "")) if info else ""
    category = info.get(constants.CATEGORY) or info.get("category")
    if not move_type or category == constants.STATUS or category == "status":
        return {
            "multiplier": None,
            "label": "status/non-damaging",
            "move_type": move_type or None,
        }

    types = _defending_types(defender)
    try:
        mult = type_effectiveness_modifier(move_type, types) if types else 1.0
    except KeyError:
        mult = 1.0

    reason_bits = []
    if mult == 0:
        reason_bits.append("type immune")
    elif mult > 1:
        reason_bits.append(f"{mult}x SE")
    elif mult < 1:
        reason_bits.append(f"{mult}x resisted")
    else:
        reason_bits.append("neutral")

    if not abilities_suppressed:
        blocked_by = _ability_blocks_type(defender.ability, move_type)
        if blocked_by:
            mult = 0.0
            reason_bits = [f"immune ({blocked_by})"]

    return {
        "multiplier": mult,
        "label": "; ".join(reason_bits),
        "move_type": move_type,
    }


def build_type_effectiveness_matrix(battle) -> dict:
    """Map each user active's damaging moves to foe-slot multipliers."""
    abilities_suppressed = bool(
        getattr(battle, "neutralizing_gas_is_active", lambda: False)()
    )
    foes = {
        "opponent_slot_a": battle.opponent.slot_a.active,
        "opponent_slot_b": battle.opponent.slot_b.active,
    }
    matrix = {}
    for slot_key, slot in (
        ("slot_a", battle.user.slot_a),
        ("slot_b", battle.user.slot_b),
    ):
        active = slot.active
        if not _alive_active(active):
            continue
        move_rows = {}
        seen = set()
        for move in active.moves:
            if move.disabled or move.name in seen:
                continue
            seen.add(move.name)
            row = {}
            for foe_key, foe in foes.items():
                if not _alive_active(foe):
                    row[foe_key] = {
                        "multiplier": None,
                        "label": "empty/fainted",
                        "move_type": None,
                    }
                else:
                    row[foe_key] = _move_vs_defender(
                        move.name, foe, abilities_suppressed
                    )
            move_rows[move.name] = row
        matrix[active.name] = move_rows
    return matrix


def build_decision_state(battle) -> dict:
    """Compact JSON snapshot + per-slot legal action whitelists."""
    legal_a = legal_actions_for_slot(battle, 0)
    # Do not pre-restrict slot B by A's choices; validation handles conflicts.
    legal_b = legal_actions_for_slot(battle, 1)

    state = {
        "turn": battle.turn,
        "weather": battle.weather,
        "field": battle.field,
        "trick_room": bool(battle.trick_room),
        "force_switch": list(battle.force_switch),
        "user_side_conditions": _side_conditions(battle.user),
        "opponent_side_conditions": _side_conditions(battle.opponent),
        "active_speed_order": build_active_speed_order(battle),
        "type_effectiveness_matrix": build_type_effectiveness_matrix(battle),
        "damage_ko_matrix": build_damage_ko_matrix(battle),
        "incoming_ko_matrix": build_incoming_ko_matrix(battle),
        "priority_threats": build_priority_threats(battle),
        "protect_status": build_protect_status(battle),
        "opponent_inferences": build_opponent_inferences(battle),
        "team_roles": build_team_roles(battle),
        "turn_plan_hints": build_turn_plan_hints(battle),
        "meta_hints": contextual_meta_hints(battle),
        "slot_a": {
            "active": _serialize_pkmn(battle.user.slot_a.active),
            "trapped": bool(getattr(battle.user.slot_a, "trapped", False)),
            "legal_actions": legal_a,
        },
        "slot_b": {
            "active": _serialize_pkmn(battle.user.slot_b.active),
            "trapped": bool(getattr(battle.user.slot_b, "trapped", False)),
            "legal_actions": legal_b,
        },
        "bench": [
            _serialize_pkmn(p, include_moves=True)
            for p in battle.user.reserve
            if p.name and p.name != "none"
        ],
        "opponent_slot_a": _serialize_pkmn(battle.opponent.slot_a.active),
        "opponent_slot_b": _serialize_pkmn(battle.opponent.slot_b.active),
        "opponent_bench": [
            _serialize_pkmn(p, include_moves=True)
            for p in battle.opponent.reserve
            if p.name and p.name != "none" and p.hp > 0
        ],
    }
    return state


def build_team_preview_state(battle) -> dict:
    party = []
    for p in _all_user_mons(battle.user):
        party.append(
            {
                "index": p.index,
                "name": p.name,
                "types": list(p.types) if p.types else [],
                "item": p.item,
                "ability": p.ability,
                "moves": [m.name for m in p.moves],
                "tera_type": p.tera_type,
            }
        )
    opponent = []
    for p in battle.opponent.reserve:
        if p.name and p.name != "none":
            opponent.append(
                {
                    "name": p.name,
                    "types": list(p.types) if p.types else [],
                    "item": p.item if p.item != constants.UNKNOWN_ITEM else None,
                    "ability": p.ability,
                    "moves": [m.name for m in p.moves] if p.moves else [],
                }
            )
    legal_digits = sorted(
        {str(p["index"]) for p in party if p["index"] is not None},
        key=lambda x: int(x),
    )
    recommendation = recommend_team_preview(battle)
    return {
        "phase": "team_preview",
        "party": party,
        "opponent": opponent,
        "opponent_inferences": build_opponent_inferences(battle),
        "team_roles": build_team_roles(battle),
        "recommended_preview": recommendation,
        "legal_indices": legal_digits,
        "instruction": (
            "Pick exactly 4 distinct party indices. "
            "Order: lead_a, lead_b, reserve_1, reserve_2. "
            "Prefer recommended_preview.digits unless you have a clear better plan. "
            'Return JSON: {"digits":"ABCD"} where each char is an index.'
        ),
    }


def _all_user_mons(user):
    mons = []
    for slot in (user.slot_a, user.slot_b):
        if slot.active and slot.active.name and slot.active.name != "none":
            mons.append(slot.active)
    for p in user.reserve:
        if p.name and p.name != "none":
            mons.append(p)
    return mons


def validate_move_choices(
    slot_a: str, slot_b: str, legal_a: list[str], legal_b: list[str]
) -> tuple[bool, str]:
    if slot_a not in legal_a:
        return False, f"slot_a action not legal: {slot_a!r}"
    if slot_b not in legal_b:
        return False, f"slot_b action not legal: {slot_b!r}"

    switch_a = (
        slot_a.split(" ", 1)[1]
        if slot_a.startswith(constants.SWITCH_STRING + " ")
        else None
    )
    switch_b = (
        slot_b.split(" ", 1)[1]
        if slot_b.startswith(constants.SWITCH_STRING + " ")
        else None
    )
    if switch_a and switch_b and normalize_name(switch_a) == normalize_name(switch_b):
        return False, "both slots switching to the same pokemon"

    tera_count = sum(1 for s in (slot_a, slot_b) if s.endswith(",tera"))
    if tera_count > 1:
        return False, "only one terastallize allowed per turn"

    return True, ""


def validate_team_preview_digits(digits: str, legal_indices: list[str]) -> tuple[bool, str]:
    if not digits or len(digits) != 4:
        return False, f"digits must be length 4, got {digits!r}"
    chars = list(digits)
    if len(set(chars)) != 4:
        return False, f"digits must be 4 distinct indices, got {digits!r}"
    for c in chars:
        if c not in legal_indices:
            return False, f"index {c!r} not in legal_indices {legal_indices}"
    return True, ""
