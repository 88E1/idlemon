"""
Fast scripted doubles policy for the "Ragoff" Charizard / Aerodactyl Team.
Returns internal choice strings consumed by fp.search.helpers.format_decision.
"""

import logging

import constants
from data import all_move_json
from fp.helpers import (
    is_replacement_request,
    normalize_name,
    type_effectiveness_modifier,
)

logger = logging.getLogger(__name__)

# Party indices for team preview (leads first, then back)
DEFAULT_TEAM = ("whimsicott", "garchomp", "charizard", "kingambit")

TR_SETTERS = set()  # No Trick Room setters on this team
FAKE_OUT_USERS = set()  # No Fake Out users on this team

SPREAD_MOVES = {
    "heatwave",
    "rockslide",
    "earthquake",
    "dazzlinggleam",
}

SELF_SIDE_MOVES = {"wideguard", "tailwind", "protect"}
ALLY_TARGET_MOVES = set()

SWITCH_PRIORITY = (
    "garchomp",
    "charizard",
    "charizardmegay",
    "charizardmega",
    "basculegion",
    "kingambit",
    "aerodactyl",
    "aerodactylmega",
    "floetteeternal",
    # Fallbacks for tests or other teams
    "blastoise",
    "blastoisemega",
    "farigiraf",
    "sinistcha",
    "incineroar",
    "pelipper",
)

# Prefer these when benching a weakened active (voluntary switch)
VOLUNTARY_SWITCH_OUT = {
    "aerodactyl",
    "aerodactylmega",
    "charizard",
    "charizardmegay",
    "charizardmega",
    "floetteeternal",
}

TR_SWEEPERS = {"kingambit"}
RAIN_ABUSERS = {"basculegion"}
PHYSICAL_THREAT_TYPES = {"fighting", "dark", "normal", "rock", "steel"}


def _species_key(pkmn):
    if pkmn is None:
        return ""
    return normalize_name(getattr(pkmn, "base_name", None) or pkmn.name)


def _all_user_mons(user):
    mons = []
    for slot in (user.slot_a, user.slot_b):
        if slot.active and slot.active.name and slot.active.name != "none":
            mons.append(slot.active)
    for p in user.reserve:
        if p.name and p.name != "none":
            mons.append(p)
    return mons


def _opponent_actives(battle):
    mons = []
    for slot in (battle.opponent.slot_a, battle.opponent.slot_b):
        p = slot.active
        if p and p.name and p.name != "none" and p.hp > 0:
            mons.append(p)
    return mons


def _index_for(user, species):
    species = normalize_name(species)
    for p in _all_user_mons(user):
        if p.name == species or p.base_name == species:
            return p.index
    return None


def pick_team_preview_digits(battle):
    from fp.vgc_intel import recommend_team_preview

    recommendation = recommend_team_preview(battle)
    result = recommendation["digits"]
    logger.info(
        "team_preview -> %s (%s) tags=%s",
        result,
        recommendation.get("reason"),
        recommendation.get("opponent_tags"),
    )
    return result


def _foe_target(slot_index):
    """Opponent slot index 0 -> side 2,a; 1 -> side 2,b."""
    return f"2,{'a' if slot_index == 0 else 'b'}"


def _ally_target(slot_index):
    return f"1,{'a' if slot_index == 0 else 'b'}"


def _move_info(name):
    return all_move_json.get(normalize_name(name), {})


def _effective_power(move_name, attacker, defender, battle=None):
    info = _move_info(move_name)
    power = info.get("basePower") or 0
    if power == 0 and info.get(constants.CATEGORY) != "Status":
        power = 60
    if move_name == "waterspout" and attacker.max_hp:
        power = max(1, int(150 * attacker.hp / attacker.max_hp))
    if move_name == "lastrespects" and battle:
        fainted_count = sum(1 for p in battle.user.reserve if p.hp <= 0 or p.fainted)
        power = 50 + 50 * fainted_count
    move_type = info.get(constants.TYPE) or "normal"
    mult = type_effectiveness_modifier(move_type, defender.types)
    stab = 1.5 if attacker.has_type(move_type) else 1.0
    return power * mult * stab


def _best_damage_move(attacker, foes, battle=None, prefer_spread=False):
    best = None
    best_score = -1
    for move in attacker.moves:
        if move.disabled or move.name in ("fakeout", "protect", "wideguard", "tailwind"):
            continue
        info = _move_info(move.name)
        target = info.get("target", "normal")
        if move.name in SPREAD_MOVES or target in ("allAdjacentFoes", "allAdjacent"):
            if prefer_spread or len(foes) > 1:
                score = sum(_effective_power(move.name, attacker, f, battle) for f in foes)
                if score > best_score:
                    best_score = score
                    best = move.name
            continue
        if move.name in SELF_SIDE_MOVES or move.name in ALLY_TARGET_MOVES:
            continue
        for i, foe in enumerate(foes[:2]):
            score = _effective_power(move.name, attacker, foe, battle)
            if score > best_score:
                best_score = score
                best = f"{move.name},{_foe_target(i)}"
    return best


def _can_fake_out_target(foe):
    return "ghost" not in foe.types


def _just_switched_in(pkmn, battle):
    if battle.turn <= 1:
        return True
    last = getattr(pkmn, "last_selected_move", None)
    if last and last.move and last.move.startswith("switch"):
        return last.turn == battle.turn
    return len(pkmn.moves_used_since_switch_in) == 0


def _on_field_species(user):
    keys = set()
    for slot in (user.slot_a, user.slot_b):
        active = slot.active
        # Only living actives block their species from switching in.
        if (
            active
            and active.name
            and active.name != "none"
            and active.hp > 0
            and not active.fainted
        ):
            keys.add(_species_key(active))
    return keys


def _partner_active(battle, slot_index):
    if slot_index == 0:
        return battle.user.slot_b.active
    return battle.user.slot_a.active


def _bench_candidates(user, exclude_species):
    out = []
    for p in user.reserve:
        if p.hp <= 0 or p.name == "none" or p.fainted:
            continue
        key = _species_key(p)
        name_key = normalize_name(p.name)
        # Exclude by species key and current forme name (mega/forme aliases).
        if key in exclude_species or name_key in exclude_species:
            continue
        out.append(p)
    return out


def _offensive_score_vs_foes(pkmn, foes, battle=None):
    if not foes or not pkmn.moves:
        return 0.0
    best = 0.0
    for move in pkmn.moves:
        if move.disabled:
            continue
        info = _move_info(move.name)
        if info.get(constants.CATEGORY) == "Status" and move.name not in SPREAD_MOVES:
            continue
        target = info.get("target", "normal")
        if move.name in SPREAD_MOVES or target in ("allAdjacentFoes", "allAdjacent"):
            score = sum(_effective_power(move.name, pkmn, f, battle) for f in foes)
        else:
            score = max(
                (_effective_power(move.name, pkmn, f, battle) for f in foes),
                default=0,
            )
        best = max(best, score)
    return best


def _priority_tiebreaker(pkmn):
    key = _species_key(pkmn)
    for i, name in enumerate(SWITCH_PRIORITY):
        if key == name:
            return len(SWITCH_PRIORITY) - i
    return 0


def _switch_in_score(pkmn, battle, partner, want_tailwind):
    score = 0.0
    key = _species_key(pkmn)
    foes = _opponent_actives(battle)
    hp_frac = pkmn.hp / pkmn.max_hp if pkmn.max_hp else 0

    score += hp_frac * 12
    score += _offensive_score_vs_foes(pkmn, foes, battle) * 0.08
    score += _priority_tiebreaker(pkmn) * 2

    # Garchomp is our key win condition, give it a high baseline score if healthy
    if key == "garchomp":
        score += 15
        if any(_species_key(f) == "basculegion" for f in foes):
            score += 10
        if battle.trick_room:
            score -= 10

    # Kingambit is great late game, and absolute beast under Trick Room
    if key == "kingambit":
        if battle.trick_room:
            score += 20
        elif len(foes) <= 2 and all(f.hp / f.max_hp < 0.5 for f in foes if f.max_hp):
            score += 18  # Sucker punch checkmate potential
        else:
            score += 8

    # Charizard sets Sun, which is amazing unless opponent has rain/sand we want to override later
    if key in ("charizard", "charizardmegay", "charizardmega"):
        score += 12
        if battle.weather == constants.RAIN:
            score += 20
        if battle.trick_room:
            score -= 10

    # Basculegion is a great late game cleaner with Last Respects
    if key == "basculegion":
        fainted_count = sum(1 for p in battle.user.reserve if p.hp <= 0 or p.fainted)
        score += fainted_count * 6
        if battle.weather == constants.SUN:
            score -= 4

    # Aerodactyl sets Tailwind
    if key in ("aerodactyl", "aerodactylmega"):
        if want_tailwind:
            score += 15
        has_spread_foe = any(any(m.name in SPREAD_MOVES for m in f.moves) for f in foes)
        if has_spread_foe:
            score += 8
        if battle.trick_room:
            score -= 15

    # Floette-Eternal has zero bulk, so we should avoid switching it in unless safe
    if key == "floetteeternal":
        if battle.user.side_conditions[constants.TAILWIND]:
            score += 6
        else:
            score -= 15

    return score


def _best_switch(battle, slot_index, already_chosen):
    on_field = _on_field_species(battle.user)
    # Never ignore already_chosen: with 1 reserve left and a double
    # force-switch, the second slot must pass instead of stealing the same mon.
    exclude = on_field | already_chosen
    candidates = _bench_candidates(battle.user, exclude)
    if not candidates:
        return None

    partner = _partner_active(battle, slot_index)
    want_tailwind = not battle.user.side_conditions[constants.TAILWIND] and any(_species_key(p) in ("aerodactyl", "aerodactylmega") for p in candidates)
    best = max(
        candidates,
        key=lambda p: _switch_in_score(p, battle, partner, want_tailwind),
    )
    logger.info(
        "switch-in slot %s -> %s (hp %.0f%%, tr=%s rain=%s)",
        slot_index,
        best.name,
        100 * best.hp / best.max_hp if best.max_hp else 0,
        battle.trick_room,
        battle.weather == constants.RAIN,
    )
    return best


def _should_voluntary_switch(battle, slot, slot_index):
    active = slot.active
    if slot.trapped or not active or active.name == "none" or active.hp <= 0:
        return False

    on_field = _on_field_species(battle.user)
    bench = _bench_candidates(battle.user, on_field)
    if not bench:
        return False

    foes = _opponent_actives(battle)
    if not foes:
        return False

    hp_frac = active.hp / active.max_hp if active.max_hp else 1

    # CRITICAL: If active has < 15% HP, do not voluntarily switch it out!
    # It's almost always better to let it attack or use utility and faint,
    # giving us a clean switch-in, rather than wasting a turn switching.
    if hp_frac < 0.15:
        return False

    # Filter bench candidates to only those that are healthy enough to switch in voluntarily
    healthy_bench = [p for p in bench if (p.hp / p.max_hp if p.max_hp else 0) >= 0.25]
    if not healthy_bench:
        return False

    partner = _partner_active(battle, slot_index)
    want_tailwind = not battle.user.side_conditions[constants.TAILWIND] and any(_species_key(p) in ("aerodactyl", "aerodactylmega") for p in bench)
    active_score = _switch_in_score(active, battle, partner, want_tailwind)
    best_bench = max(
        healthy_bench, key=lambda p: _switch_in_score(p, battle, partner, want_tailwind)
    )
    best_bench_score = _switch_in_score(best_bench, battle, partner, want_tailwind)

    key = _species_key(active)

    # If active is Floette-Eternal and it is threatened (or low HP), switch it out! It has zero bulk.
    if key == "floetteeternal":
        if hp_frac < 0.8 or any(type_effectiveness_modifier(_move_info(m.name).get(constants.TYPE, "normal").lower(), active.types) > 1.0 for f in foes for m in f.moves if m.name):
            if best_bench_score > active_score + 5:
                return True

    # If active is very low on HP
    if hp_frac < 0.2 and best_bench_score > active_score + 4:
        return True

    # If active has very low offensive presence vs current foes
    active_off = _offensive_score_vs_foes(active, foes, battle)
    if active_off < 30 and best_bench_score > active_score + 10:
        return True

    return False


def _pick_slot(battle, slot, slot_index, force_switch, already_chosen):
    active = slot.active
    # Pure faint-replacement turns: non-switching slots must pass.
    if is_replacement_request(battle) and not force_switch:
        return "no move"

    if force_switch or (active and (active.hp <= 0 or active.fainted)):
        repl = _best_switch(battle, slot_index, already_chosen)
        if repl:
            logger.info(
                "force-switch slot %s -> %s",
                slot_index,
                repl.name,
            )
            return f"{constants.SWITCH_STRING} {repl.name}"
        return "no move"

    if not active or active.name == "none":
        return "no move"

    if _should_voluntary_switch(battle, slot, slot_index):
        repl = _best_switch(battle, slot_index, already_chosen)
        if repl:
            logger.info(
                "voluntary switch slot %s: %s out -> %s in",
                slot_index,
                active.name,
                repl.name,
            )
            return f"{constants.SWITCH_STRING} {repl.name}"

    if active.status in ("slp", "frz"):
        return "no move"

    foes = _opponent_actives(battle)
    if not foes:
        return "no move"

    name = active.name

    # 1. Aerodactyl / Aerodactyl-Mega
    if name in ("aerodactyl", "aerodactylmega"):
        tw = active.get_move("tailwind")
        if not battle.user.side_conditions[constants.TAILWIND] and tw and not tw.disabled and not battle.trick_room:
            return "tailwind"

        partner = _partner_active(battle, slot_index)
        partner_key = _species_key(partner) if partner else ""
        wg = active.get_move("wideguard")
        if wg and not wg.disabled and partner_key in ("charizard", "charizardmegay", "charizardmega", "floetteeternal"):
            common_spread_users = {"garchomp", "charizard", "charizardmegay", "charizardmega", "basculegion", "pelipper", "whimsicott", "landorustherian", "sneasler", "chiyu", "gholdengo"}
            has_spread_threat = False
            for f in foes:
                f_key = _species_key(f)
                if f_key in common_spread_users:
                    has_spread_threat = True
                for m in f.moves:
                    if m.name in SPREAD_MOVES:
                        has_spread_threat = True
            if has_spread_threat:
                return "wideguard"

        rs = active.get_move("rockslide")
        if rs and not rs.disabled:
            return "rockslide"

    # 2. Charizard / Charizard-Mega-Y
    if name in ("charizard", "charizardmegay", "charizardmega"):
        sb = active.get_move("solarbeam")
        is_sun = (battle.weather == constants.SUN) or (name == "charizard" and active.can_mega_evo)
        if sb and not sb.disabled and is_sun:
            for i, f in enumerate(foes[:2]):
                if any(t in ("water", "ground", "rock") for t in f.types):
                    return f"solarbeam,{_foe_target(i)}"

        wb = active.get_move("weatherball")
        if wb and not wb.disabled and is_sun:
            best_target_idx = 0
            best_mult = -1
            for i, f in enumerate(foes[:2]):
                mult = type_effectiveness_modifier("fire", f.types)
                if mult > best_mult:
                    best_mult = mult
                    best_target_idx = i
            return f"weatherball,{_foe_target(best_target_idx)}"

        hw = active.get_move("heatwave")
        if hw and not hw.disabled:
            return "heatwave"

    # 3. Garchomp
    if name == "garchomp":
        # Check if there is a Ground-weak foe or Archaludon
        has_ground_weak_foe = False
        ground_weak_idx = None
        for i, f in enumerate(foes[:2]):
            f_key = _species_key(f)
            if f_key == "archaludon" or type_effectiveness_modifier("ground", f.types) > 1.0:
                has_ground_weak_foe = True
                ground_weak_idx = i
                break

        # We prefer Earthquake if partner is immune and there is a ground-weak foe
        eq = active.get_move("earthquake")
        partner = _partner_active(battle, slot_index)
        partner_key = _species_key(partner) if partner else ""
        partner_immune = partner_key in ("aerodactyl", "aerodactylmega", "charizard", "charizardmegay", "charizardmega")
        
        if eq and not eq.disabled and partner_immune and has_ground_weak_foe:
            return "earthquake"

        # Otherwise, if we have Stomping Tantrum and there is a ground-weak foe, use it!
        st = active.get_move("stompingtantrum")
        if st and not st.disabled and has_ground_weak_foe and ground_weak_idx is not None:
            return f"stompingtantrum,{_foe_target(ground_weak_idx)}"

        # Otherwise, try Scale Shot on non-Fairy, non-Archaludon targets
        ss = active.get_move("scaleshot")
        if ss and not ss.disabled:
            valid_targets = []
            for i, f in enumerate(foes[:2]):
                if "fairy" not in f.types and _species_key(f) != "archaludon":
                    valid_targets.append(i)
            if valid_targets:
                return f"scaleshot,{_foe_target(valid_targets[0])}"

        # Fallbacks:
        if eq and not eq.disabled and partner_immune:
            return "earthquake"

        if st and not st.disabled:
            best_target_idx = 0
            best_mult = -1
            for i, f in enumerate(foes[:2]):
                mult = type_effectiveness_modifier("ground", f.types)
                if mult > best_mult:
                    best_mult = mult
                    best_target_idx = i
            return f"stompingtantrum,{_foe_target(best_target_idx)}"

        lk = active.get_move("lowkick")
        if lk and not lk.disabled:
            best_target_idx = 0
            best_mult = -1
            for i, f in enumerate(foes[:2]):
                mult = type_effectiveness_modifier("fighting", f.types)
                if mult > best_mult:
                    best_mult = mult
                    best_target_idx = i
            return f"lowkick,{_foe_target(best_target_idx)}"

        rs = active.get_move("rockslide")
        if rs and not rs.disabled:
            return "rockslide"

    # 4. Kingambit
    if name == "kingambit":
        sp = active.get_move("suckerpunch")
        if sp and not sp.disabled:
            for i, f in enumerate(foes[:2]):
                if f.hp / f.max_hp < 0.25 if f.max_hp else False:
                    return f"suckerpunch,{_foe_target(i)}"

        kc = active.get_move("kowtowcleave")
        if kc and not kc.disabled:
            best_target_idx = 0
            best_mult = -1
            for i, f in enumerate(foes[:2]):
                mult = type_effectiveness_modifier("dark", f.types)
                if mult > best_mult:
                    best_mult = mult
                    best_target_idx = i
            return f"kowtowcleave,{_foe_target(best_target_idx)}"

        lk = active.get_move("lowkick")
        if lk and not lk.disabled:
            best_target_idx = 0
            best_mult = -1
            for i, f in enumerate(foes[:2]):
                mult = type_effectiveness_modifier("fighting", f.types)
                if mult > best_mult:
                    best_mult = mult
                    best_target_idx = i
            return f"lowkick,{_foe_target(best_target_idx)}"

    # 5. Basculegion
    if name == "basculegion":
        aj = active.get_move("aquajet")
        if aj and not aj.disabled:
            for i, f in enumerate(foes[:2]):
                if f.hp / f.max_hp < 0.2 if f.max_hp else False:
                    return f"aquajet,{_foe_target(i)}"

        lr = active.get_move("lastrespects")
        fainted_count = sum(1 for p in battle.user.reserve if p.hp <= 0 or p.fainted)
        if lr and not lr.disabled and fainted_count >= 1:
            best_target_idx = 0
            best_mult = -1
            for i, f in enumerate(foes[:2]):
                mult = type_effectiveness_modifier("ghost", f.types)
                if mult > best_mult:
                    best_mult = mult
                    best_target_idx = i
            return f"lastrespects,{_foe_target(best_target_idx)}"

        wc = active.get_move("wavecrash")
        if wc and not wc.disabled and battle.weather != constants.SUN:
            best_target_idx = 0
            best_mult = -1
            for i, f in enumerate(foes[:2]):
                mult = type_effectiveness_modifier("water", f.types)
                if mult > best_mult:
                    best_mult = mult
                    best_target_idx = i
            return f"wavecrash,{_foe_target(best_target_idx)}"

        ft = active.get_move("flipturn")
        if ft and not ft.disabled:
            return f"flipturn,{_foe_target(0)}"

    # 6. Floette-Eternal
    if name == "floetteeternal":
        lor = active.get_move("lightofruin")
        if lor and not lor.disabled:
            best_target_idx = 0
            best_mult = -1
            for i, f in enumerate(foes[:2]):
                mult = type_effectiveness_modifier("fairy", f.types)
                if mult > best_mult:
                    best_mult = mult
                    best_target_idx = i
            return f"lightofruin,{_foe_target(best_target_idx)}"

        mb = active.get_move("moonblast")
        if mb and not mb.disabled:
            best_target_idx = 0
            best_mult = -1
            for i, f in enumerate(foes[:2]):
                mult = type_effectiveness_modifier("fairy", f.types)
                if mult > best_mult:
                    best_mult = mult
                    best_target_idx = i
            return f"moonblast,{_foe_target(best_target_idx)}"

        dg = active.get_move("dazzlinggleam")
        if dg and not dg.disabled:
            return "dazzlinggleam"

    best = _best_damage_move(active, foes, battle, prefer_spread=len(foes) > 1)
    if best:
        return best

    # Fallback: first enabled move
    for move in active.moves:
        if not move.disabled:
            info = _move_info(move.name)
            if info.get("target") in ("allAdjacentFoes", "allAdjacent", "all"):
                return move.name
            return f"{move.name},{_foe_target(0)}"
    return "no move"


def _record_switch_choice(choice, already_chosen, user=None):
    if not choice.startswith(constants.SWITCH_STRING + " "):
        return
    name = choice.split("switch ", 1)[1]
    already_chosen.add(normalize_name(name))
    if user is None:
        return
    # Also exclude by species key so mega/forme names can't be double-picked.
    for p in list(user.reserve) + [
        getattr(user.slot_a, "active", None),
        getattr(user.slot_b, "active", None),
    ]:
        if not p or not p.name or p.name == "none":
            continue
        if normalize_name(p.name) == normalize_name(name) or normalize_name(
            getattr(p, "base_name", "")
        ) == normalize_name(name):
            already_chosen.add(_species_key(p))
            already_chosen.add(normalize_name(p.name))
            break


def pick_moves(battle):
    fs = battle.force_switch
    already_chosen = set()
    choice_a = _pick_slot(battle, battle.user.slot_a, 0, fs[0], already_chosen)
    _record_switch_choice(choice_a, already_chosen, battle.user)
    choice_b = _pick_slot(battle, battle.user.slot_b, 1, fs[1], already_chosen)
    logger.debug("turn %s -> %s | %s", battle.turn, choice_a, choice_b)
    return choice_a, choice_b
