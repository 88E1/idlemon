"""
Competitive VGC helpers for LLM/heuristic decisions:
damage/KO estimates, opponent set guesses, team roles, preview leads.
"""

from __future__ import annotations

import constants
from data import all_move_json
from fp.helpers import normalize_name, type_effectiveness_modifier

# Our current sample team roles (Champions Reg M-B).
TEAM_ROLES = {
    "whimsicott": "Speed control (Prankster Tailwind) / Encore / soft Fairy damage",
    "charizard": "Sun setter via Mega Y; Drought breaker (Heat Wave / Weather Ball / Solar Beam)",
    "charizardmegay": "Sun setter via Mega Y; Drought breaker (Heat Wave / Weather Ball / Solar Beam)",
    "garchomp": "Physical spread breaker (EQ / Rock Slide); late-game cleaner",
    "kingambit": "Late-game Defiant wallbreaker; Sucker Punch priority; TR-friendly",
    "basculegion": "Adaptability cleaner; Last Respects scales with our KOs; Aqua Jet prio",
    "floetteeternal": "Mega Fairy nuke (Light of Ruin); fragile — need speed control first",
    "floette": "Mega Fairy nuke (Light of Ruin); fragile — need speed control first",
}

# Common Champions / VGC doubles sets we care about.
OPPONENT_SETS = {
    "incineroar": {
        "ability": "intimidate",
        "items": ["safetygoggles", "assaultvest", "figyberry"],
        "moves": ["fakeout", "flareblitz", "knockoff", "partingshot", "uturn"],
        "threat": "T1 Fake Out + Intimidate. Protect or switch into Defiant.",
    },
    "lopunny": {
        "ability": "limber",
        "items": ["lopunnite"],
        "moves": ["fakeout", "highjumpkick", "closecombat", "uturn", "encore"],
        "threat": "Mega Fake Out + Fighting STAB. Protect Kingambit; KO early.",
    },
    "lopunnymega": {
        "ability": "scrappy",
        "items": ["lopunnite"],
        "moves": ["fakeout", "highjumpkick", "closecombat", "uturn"],
        "threat": "Scrappy Fake Out hits Ghosts. Fast Fighting nuke.",
    },
    "torkoal": {
        "ability": "drought",
        "items": ["charcoal", "heatrock", "lifeorb"],
        "moves": ["eruption", "heatwave", "solarbeam", "protect", "yawn"],
        "threat": "Sun Eruption. Outspeed or Protect; Chlorophyll partners are scary.",
    },
    "vileplume": {
        "ability": "chlorophyll",
        "items": ["lifeorb", "focus sash"],
        "moves": ["sleeppowder", "sludgebomb", "gigadrain", "afteryou", "strengthsap"],
        "threat": "Sun Sleep Powder + After You. Don't leave Zard exposed in sun.",
    },
    "sylveon": {
        "ability": "pixilate",
        "items": ["lifeorb", "choicespecs", "assaultvest"],
        "moves": ["hypervoice", "moonblast", "protect", "mysticalfire", "quickattack"],
        "threat": "Pixilate Hyper Voice spreads hard. Steel resists; Kingambit walls.",
    },
    "farigiraf": {
        "ability": "armor tail",
        "items": ["mentalherb", "sitrusberry"],
        "moves": ["trickroom", "psychic", "helpinghand", "protect", "dazzlinggleam"],
        "threat": "TR setter with Armor Tail. Encore / pressure before TR goes up.",
    },
    "gengar": {
        "ability": "cursedbody",
        "items": ["gengarite"],
        "moves": ["shadowball", "sludgebomb", "perishsong", "protect", "disable"],
        "threat": "Mega Shadow Tag traps both. KO it or perish expires.",
    },
    "gengarmega": {
        "ability": "shadowtag",
        "items": ["gengarite"],
        "moves": ["shadowball", "sludgebomb", "perishsong", "protect"],
        "threat": "Shadow Tag + Perish. Must KO or perish race.",
    },
    "rillaboom": {
        "ability": "grassysurge",
        "items": ["assaultvest", "lifeorb"],
        "moves": ["fakeout", "woodhammer", "grassyglide", "uturn", "knockoff"],
        "threat": "Fake Out + Grassy Glide prio. Fire answers (Zard) are excellent.",
    },
    "archaludon": {
        "ability": "stamina",
        "items": ["assaultvest", "lifeorb"],
        "moves": ["bodypress", "flashcannon", "snarl", "electroshot", "protect"],
        "threat": "Stamina Body Press tank. Ground (Garchomp) or Fighting needed.",
    },
    "pelipper": {
        "ability": "drizzle",
        "items": ["mysticwater", "damprock"],
        "moves": ["hurricane", "hydropump", "tailwind", "protect", "wideguard"],
        "threat": "Rain setter. Contest weather with Mega Y or pressure Pelipper.",
    },
    "mawile": {
        "ability": "intimidate",
        "items": ["mawilite"],
        "moves": ["playrough", "suckerpunch", "ironhead", "swordsdance", "protect"],
        "threat": "Mega Huge Power. Fire (Zard) or Ground answers.",
    },
    "mawilemega": {
        "ability": "hugepower",
        "items": ["mawilite"],
        "moves": ["playrough", "suckerpunch", "ironhead", "swordsdance"],
        "threat": "Huge Power Mega Mawile. Fire resists Play Rough poorly — KO fast.",
    },
    "sinistcha": {
        "ability": "hospitality",
        "items": ["sitrusberry", "rockyhelmet"],
        "moves": ["matchagotcha", "ragepowder", "trickroom", "strengthsap", "protect"],
        "threat": "Hospitality heals partner on switch. Punish the switch-in.",
    },
    "ursaluna": {
        "ability": "guts",
        "items": ["flameorb", "lifeorb"],
        "moves": ["facade", "headlongrush", "protect", "earthquake", "swordsdance"],
        "threat": "Guts Facade + Headlong Rush. Ghost/Flying evade or Protect.",
    },
    "ursalunabloodmoon": {
        "ability": "mindseye",
        "items": ["lifeorb", "choicespecs"],
        "moves": ["bloodmoon", "earthpower", "hypervoice", "protect", "vacuumwave"],
        "threat": "Huge special nuke. Pressure before it clicks Blood Moon.",
    },
    "calyrexice": {
        "ability": "asoneofice",
        "items": ["clearamulet", "weaknesspolicy"],
        "moves": ["glaciallance", "trickroom", "protect", "highhorsepower", "substitute"],
        "threat": "TR Glacial Lance. Encore / Fake pressure before TR.",
    },
    "fluttermane": {
        "ability": "protosynthesis",
        "items": ["boosterenergy", "choicespecs", "focus sash"],
        "moves": ["moonblast", "shadowball", "dazzlinggleam", "protect", "icywind"],
        "threat": "Sun-boosted Fairy/Ghost. Kingambit resists Fairy.",
    },
    "vanilluxe": {
        "ability": "snowwarning",
        "items": ["icyrock", "focussash", "lifeorb"],
        "moves": ["blizzard", "freezedry", "iceshard", "protect", "auroraveil"],
        "threat": "Hail Blizzard + Ice Shard priority. Never assume outspeed = safe vs Ice Shard.",
    },
    "camerupt": {
        "ability": "solidrock",
        "items": ["cameruptite", "lifeorb", "charcoal"],
        "moves": ["eruption", "heatwave", "earthpower", "ancientpower", "protect"],
        "threat": "Mega Eruption scales with HP — chip first. Rock move deletes Zard.",
    },
    "cameruptmega": {
        "ability": "sheerforce",
        "items": ["cameruptite"],
        "moves": ["eruption", "heatwave", "earthpower", "ancientpower", "protect"],
        "threat": "Sheer Force Mega Camerupt. Chip HP to gut Eruption; watch Ancient Power vs Zard.",
    },
    "blastoise": {
        "ability": "torrent",
        "items": ["blastoisinite", "sitrusberry", "choicespecs"],
        "moves": ["waterpulse", "icespinner", "darkpulse", "aurasphere", "protect"],
        "threat": "Mega Mega Launcher spreads. Grass (Solar Beam) answers well in sun.",
    },
    "blastoisemega": {
        "ability": "megalauncher",
        "items": ["blastoisinite"],
        "moves": ["waterpulse", "darkpulse", "aurasphere", "dragonpulse", "protect"],
        "threat": "Mega Launcher pulses. Prefer Grass/Electric answers.",
    },
    "staraptor": {
        "ability": "intimidate",
        "items": ["choicescarf", "lifeorb", "focussash"],
        "moves": ["uturn", "closecombat", "bravebird", "finalgambit", "tailwind"],
        "threat": "Intimidate pivot. Protect Defiant gambit; watch Close Combat / Final Gambit.",
    },
    "avalugghisui": {
        "ability": "sturdy",
        "items": ["leftovers", "rockyhelmet", "assaultvest"],
        "moves": ["mountaingale", "rockslide", "bodypress", "protect", "recover"],
        "threat": "Sturdy wall — first hit never KOs. Chip then finish; TR-friendly.",
    },
    "decidueyehisui": {
        "ability": "scrappy",
        "items": ["choicescarf", "lifeorb", "focussash"],
        "moves": ["triplearrows", "suckerpunch", "leafblade", "uturn", "protect"],
        "threat": "Scrappy Fighting + Sucker Punch prio. Protect or outpace with Tailwind.",
    },
    "kingambit": {
        "ability": "defiant",
        "items": ["blackglasses", "assaultvest", "focussash"],
        "moves": ["kowtowcleave", "suckerpunch", "ironhead", "swordsdance", "protect"],
        "threat": "Defiant + Sucker Punch endgame. Fake Out / chip before it cleans.",
    },
    "grimmsnarl": {
        "ability": "prankster",
        "items": ["lightclay", "sitrusberry"],
        "moves": ["reflect", "lightscreen", "spiritbreak", "thunderwave", "foulplay"],
        "threat": "Prankster screens. Break screens or Encore; Spirit Break cuts SpA.",
    },
    "slowbro": {
        "ability": "oblivious",
        "items": ["slowbronite", "leftovers", "rockyhelmet"],
        "moves": ["trickroom", "scald", "psychic", "slackoff", "protect"],
        "threat": "Mega TR / Calm Mind tank. Encore lock or pressure before setup.",
    },
    "slowbromega": {
        "ability": "shellarmor",
        "items": ["slowbronite"],
        "moves": ["trickroom", "scald", "psychic", "calmmind", "slackoff"],
        "threat": "Shell Armor Mega Slowbro. Encore Calm Mind; don't let it stack.",
    },
    "tyranitar": {
        "ability": "sandstream",
        "items": ["tyranitarite", "assaultvest", "weaknesspolicy"],
        "moves": ["rockslide", "crunch", "earthquake", "icepunch", "protect"],
        "threat": "Sand setter. Fighting/Ground answers; watch Rock Slide flinch.",
    },
    "tyranitarmega": {
        "ability": "sandstream",
        "items": ["tyranitarite"],
        "moves": ["rockslide", "crunch", "earthquake", "icepunch", "protect"],
        "threat": "Mega Ttar sand. Prefer Fighting STAB or special Grass.",
    },
    "aggron": {
        "ability": "sturdy",
        "items": ["aggronite", "leftovers"],
        "moves": ["heavyslam", "bodypress", "earthquake", "stealthrock", "protect"],
        "threat": "Mega filter. Fighting/Ground; Encore Body Press if locked.",
    },
    "aggronmega": {
        "ability": "filter",
        "items": ["aggronite"],
        "moves": ["heavyslam", "bodypress", "earthquake", "roar", "protect"],
        "threat": "Filter Mega Aggron. Encore / chip; Fighting still best answer.",
    },
}

_TR_SETTERS = {
    "farigiraf",
    "slowkinggalar",
    "slowking",
    "cresselia",
    "porygon2",
    "hatterene",
    "oranguru",
    "bronzong",
    "reuniclus",
    "mimikyu",
    "calyrexice",
    "indeedee",
    "indeedeef",
    "dusclops",
    "dusknoir",
}
_FAKEOUT = {
    "incineroar",
    "lopunny",
    "lopunnymega",
    "rillaboom",
    "scrafty",
    "sneasler",
    "kangaskhan",
    "kangaskhanmega",
    "weavile",
}
_SUN = {"torkoal", "ninetales", "groudon", "chiyu", "lilligant", "lilliganthisui"}
_RAIN = {"pelipper", "politoed", "kyogre", "barraskewda"}
_SHADOW_TAG = {"gengar", "gengarmega", "wobbuffet", "wynaut", "gothitelle"}
_CHLOROPHYLL = {"vileplume", "venusaur", "venusaurmega", "lilligant", "tsareena", "whimsicott"}

BASE_META_HINTS = [
    "Use active_speed_order for turn order (Trick Room reverses it).",
    "Check priority_threats — foe priority (Ice Shard / Sucker Punch / Fake Out) moves before speed.",
    "Use incoming_ko_matrix: if a foe can KO you before you move, Protect or pivot.",
    "Prefer damage_ko_matrix ko_chance of likely/guaranteed; avoid immune (0.0).",
    "Protect on predicted Fake Out / double-target turns; don't Protect into nothing.",
    "If protect_status says consecutive_protect_risky, prefer attacking or switching.",
    "Preserve Tailwind / Drought when they are your win condition.",
    "With 1–2 mons left: attack or Protect — never invent illegal switches.",
    "Click priority (Sucker Punch / Aqua Jet) into slower KO range targets.",
]

# Moves that always have priority > 0 (Grassy Glide handled dynamically).
_ALWAYS_PRIORITY = {
    "fakeout",
    "firstimpression",
    "extremespeed",
    "iceshard",
    "suckerpunch",
    "aquajet",
    "bulletpunch",
    "machpunch",
    "shadowsneak",
    "quickattack",
    "vacuumwave",
    "watershuriken",
    "accelerock",
    "jetpunch",
    "thunderclap",
    "upperhand",
}

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

_SPREAD_TARGETS = {"allAdjacentFoes", "allAdjacent", "all"}


def _species(pkmn) -> str:
    if pkmn is None:
        return ""
    return normalize_name(getattr(pkmn, "base_name", None) or pkmn.name)


def _alive(pkmn) -> bool:
    return bool(
        pkmn
        and pkmn.name
        and pkmn.name != "none"
        and pkmn.hp > 0
        and not pkmn.fainted
    )


def _move_info(move_name: str) -> dict:
    return all_move_json.get(normalize_name(move_name), {}) or {}


def _move_priority(move_name: str, battle) -> int:
    """Effective priority for a move given current field (Grassy Glide)."""
    name = normalize_name(move_name)
    info = _move_info(name)
    try:
        prio = int(info.get("priority") or 0)
    except (TypeError, ValueError):
        prio = 0
    field = normalize_name(getattr(battle, "field", None) or "")
    if name == "grassyglide" and "grassy" in field:
        prio = max(prio, 1)
    if name in _ALWAYS_PRIORITY:
        prio = max(prio, 1 if name != "fakeout" else 3)
        if name == "extremespeed":
            prio = max(prio, 2)
        if name == "firstimpression":
            prio = max(prio, 2)
        if name == "fakeout":
            prio = max(prio, 3)
    return prio


def _likely_moves_for(pkmn) -> list[str]:
    info = infer_opponent_pokemon(pkmn) or {}
    moves = list(info.get("likely_moves") or [])
    if not moves:
        moves = [m.name for m in (pkmn.moves or [])]
    return [normalize_name(m) for m in moves if m]


def _protect_level(pkmn) -> int:
    if not pkmn:
        return 0
    durations = getattr(pkmn, "volatile_status_durations", None) or {}
    try:
        return int(durations.get(constants.PROTECT, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _living_user_count(battle) -> int:
    living = 0
    for p in [
        battle.user.slot_a.active,
        battle.user.slot_b.active,
        *list(battle.user.reserve),
    ]:
        if _alive(p):
            living += 1
    return living


def _defending_types(pkmn) -> list[str]:
    if pkmn.terastallized and pkmn.tera_type:
        return [normalize_name(pkmn.tera_type)]
    return [normalize_name(t) for t in (pkmn.types or [])]


def _ability_blocks(ability: str | None, move_type: str) -> bool:
    if not ability or not move_type:
        return False
    blocked = _TYPE_IMMUNITY_ABILITIES.get(normalize_name(ability))
    return bool(blocked and normalize_name(move_type) in blocked)


def _effective_move_type(move_name: str, attacker, battle) -> str:
    info = _move_info(move_name)
    move_type = normalize_name(info.get(constants.TYPE) or info.get("type") or "normal")
    name = normalize_name(move_name)
    weather = getattr(battle, "weather", None)
    if name == "weatherball":
        if weather == constants.SUN:
            return "fire"
        if weather == constants.RAIN:
            return "water"
        if weather == constants.SAND:
            return "rock"
        if weather in getattr(constants, "HAIL_OR_SNOW", ()):
            return "ice"
    ability = normalize_name(attacker.ability) if attacker.ability else ""
    if ability == "pixilate" and move_type == "normal":
        return "fairy"
    if ability == "aerilate" and move_type == "normal":
        return "flying"
    if ability == "refrigerate" and move_type == "normal":
        return "ice"
    if ability == "galvanize" and move_type == "normal":
        return "electric"
    return move_type


def _base_power(move_name: str, attacker, battle) -> int:
    info = _move_info(move_name)
    power = int(info.get("basePower") or 0)
    name = normalize_name(move_name)
    if name in ("eruption", "waterspout") and attacker.max_hp:
        power = max(1, int(150 * attacker.hp / attacker.max_hp))
    elif name == "lastrespects" and battle is not None:
        fainted = 0
        for p in list(battle.user.reserve) + [
            battle.user.slot_a.active,
            battle.user.slot_b.active,
        ]:
            if p and (p.hp <= 0 or p.fainted):
                fainted += 1
        power = 50 + 50 * fainted
    elif name == "weatherball":
        weather = getattr(battle, "weather", None) if battle is not None else None
        if weather in (
            constants.SUN,
            constants.RAIN,
            constants.SAND,
        ) or weather in getattr(constants, "HAIL_OR_SNOW", ()):
            power = 100
    elif power == 0 and (info.get(constants.CATEGORY) or "").lower() != "status":
        power = 60
    return power


def _item_boost(item: str | None, move_type: str, category: str) -> float:
    item = normalize_name(item) if item else ""
    if not item or item in ("unknownitem", "none"):
        return 1.0
    if item == "lifeorb":
        return 1.3
    if item == "choicespecs" and category == constants.SPECIAL:
        return 1.5
    if item == "choiceband" and category == constants.PHYSICAL:
        return 1.5
    type_items = {
        "charcoal": "fire",
        "mysticwater": "water",
        "miracleseed": "grass",
        "magnet": "electric",
        "nevermeltice": "ice",
        "blackglasses": "dark",
        "blackbelt": "fighting",
        "softsand": "ground",
        "hardstone": "rock",
        "spelltag": "ghost",
        "dragonfang": "dragon",
        "silkscarf": "normal",
        "sharpbeak": "flying",
        "poisonbarb": "poison",
        "twistedspoon": "psychic",
        "metalcoat": "steel",
        "fairyfeather": "fairy",
    }
    if type_items.get(item) == move_type:
        return 1.2
    return 1.0


def estimate_damage(
    attacker, defender, move_name: str, battle, *, is_spread: bool | None = None
) -> dict | None:
    """
    Approximate Gen-9 damage range as % of defender max HP.
    Returns None for status / non-damaging moves.
    """
    if not _alive(attacker) or not _alive(defender):
        return None
    info = _move_info(move_name)
    category = info.get(constants.CATEGORY) or info.get("category") or ""
    if str(category).lower() == "status" or category == constants.STATUS:
        return None

    power = _base_power(move_name, attacker, battle)
    if power <= 0:
        return None

    move_type = _effective_move_type(move_name, attacker, battle)
    if _ability_blocks(defender.ability, move_type):
        return {
            "move": normalize_name(move_name),
            "target": defender.name,
            "type": move_type,
            "mult": 0.0,
            "dmg_pct_min": 0.0,
            "dmg_pct_max": 0.0,
            "ko_chance": "immune",
        }

    types = _defending_types(defender)
    try:
        type_mult = type_effectiveness_modifier(move_type, types) if types else 1.0
    except KeyError:
        type_mult = 1.0
    if type_mult == 0:
        return {
            "move": normalize_name(move_name),
            "target": defender.name,
            "type": move_type,
            "mult": 0.0,
            "dmg_pct_min": 0.0,
            "dmg_pct_max": 0.0,
            "ko_chance": "immune",
        }

    boosted = attacker.calculate_boosted_stats()
    def_boosted = defender.calculate_boosted_stats()
    if category == constants.PHYSICAL or str(category).lower() == "physical":
        atk = float(boosted.get(constants.ATTACK, 100))
        defense = float(def_boosted.get(constants.DEFENSE, 100))
        cat = constants.PHYSICAL
    else:
        atk = float(boosted.get(constants.SPECIAL_ATTACK, 100))
        defense = float(def_boosted.get(constants.SPECIAL_DEFENSE, 100))
        cat = constants.SPECIAL
    defense = max(1.0, defense)

    level = getattr(attacker, "level", 50) or 50
    base = (((2 * level / 5 + 2) * power * (atk / defense)) / 50.0) + 2.0

    # STAB
    stab = 1.0
    if attacker.has_type(move_type):
        ability = normalize_name(attacker.ability) if attacker.ability else ""
        stab = 2.0 if ability == "adaptability" else 1.5

    weather_mod = 1.0
    weather = getattr(battle, "weather", None)
    if weather == constants.SUN:
        if move_type == "fire":
            weather_mod = 1.5
        elif move_type == "water":
            weather_mod = 0.5
    elif weather == constants.RAIN:
        if move_type == "water":
            weather_mod = 1.5
        elif move_type == "fire":
            weather_mod = 0.5

    target = info.get("target", "normal")
    if is_spread is None:
        is_spread = target in _SPREAD_TARGETS
    spread_mod = 0.75 if is_spread else 1.0

    item_mod = _item_boost(attacker.item, move_type, cat)
    # Mega stones / leftover unknown items: mild optimism for known megas
    if normalize_name(attacker.name) in ("charizardmegay",) and move_type == "fire":
        item_mod = max(item_mod, 1.0)

    modifiers = stab * type_mult * weather_mod * spread_mod * item_mod
    dmg_max = base * modifiers
    dmg_min = dmg_max * 0.85

    max_hp = float(defender.max_hp or 1)
    cur_hp = float(defender.hp or 0)
    pct_min = round(100.0 * dmg_min / max_hp, 1)
    pct_max = round(100.0 * dmg_max / max_hp, 1)
    abs_min = dmg_min
    abs_max = dmg_max

    if abs_min >= cur_hp:
        ko = "guaranteed"
    elif abs_max >= cur_hp:
        ko = "likely"
    elif abs_max >= cur_hp * 0.5 or pct_max >= 50:
        ko = "chip"
    else:
        ko = "low"

    return {
        "move": normalize_name(move_name),
        "target": defender.name,
        "type": move_type,
        "mult": type_mult,
        "dmg_pct_min": pct_min,
        "dmg_pct_max": pct_max,
        "ko_chance": ko,
    }


def build_damage_ko_matrix(battle) -> dict:
    """Per user-active damaging move vs each living foe: damage % + KO label."""
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
        if not _alive(active):
            continue
        rows = {}
        for move in active.moves:
            if move.disabled:
                continue
            row = {}
            any_damage = False
            for foe_key, foe in foes.items():
                if not _alive(foe):
                    row[foe_key] = {"ko_chance": "empty"}
                    continue
                est = estimate_damage(active, foe, move.name, battle)
                if est is None:
                    row[foe_key] = {"ko_chance": "status"}
                else:
                    any_damage = True
                    row[foe_key] = {
                        "dmg_pct": [est["dmg_pct_min"], est["dmg_pct_max"]],
                        "ko_chance": est["ko_chance"],
                        "mult": est["mult"],
                        "type": est["type"],
                    }
            if any_damage:
                rows[move.name] = row
        matrix[active.name] = rows
    return matrix


def build_incoming_ko_matrix(battle) -> dict:
    """Per opponent-active damaging move vs each living user active."""
    ours = {
        "slot_a": battle.user.slot_a.active,
        "slot_b": battle.user.slot_b.active,
    }
    matrix = {}
    for slot_key, slot in (
        ("opponent_slot_a", battle.opponent.slot_a),
        ("opponent_slot_b", battle.opponent.slot_b),
    ):
        active = slot.active
        if not _alive(active):
            continue
        rows = {}
        for move_name in _likely_moves_for(active):
            row = {}
            any_damage = False
            for our_key, ours_pkmn in ours.items():
                if not _alive(ours_pkmn):
                    row[our_key] = {"ko_chance": "empty"}
                    continue
                est = estimate_damage(active, ours_pkmn, move_name, battle)
                if est is None:
                    row[our_key] = {"ko_chance": "status"}
                else:
                    any_damage = True
                    row[our_key] = {
                        "dmg_pct": [est["dmg_pct_min"], est["dmg_pct_max"]],
                        "ko_chance": est["ko_chance"],
                        "mult": est["mult"],
                        "type": est["type"],
                        "priority": _move_priority(move_name, battle),
                    }
            if any_damage:
                rows[move_name] = row
        matrix[active.name] = rows
    return matrix


def build_priority_threats(battle) -> list[dict]:
    """
    Foe moves that can act before natural speed order and threaten our actives.
    Critical for Ice Shard / Sucker Punch / Fake Out endgames.
    """
    threats = []
    ours = {
        "slot_a": battle.user.slot_a.active,
        "slot_b": battle.user.slot_b.active,
    }
    for slot_label, slot in (
        ("opponent_slot_a", battle.opponent.slot_a),
        ("opponent_slot_b", battle.opponent.slot_b),
    ):
        attacker = slot.active
        if not _alive(attacker):
            continue
        for move_name in _likely_moves_for(attacker):
            prio = _move_priority(move_name, battle)
            if prio <= 0:
                continue
            for our_key, defender in ours.items():
                if not _alive(defender):
                    continue
                est = estimate_damage(attacker, defender, move_name, battle)
                if est is None or est.get("ko_chance") == "immune":
                    continue
                threats.append(
                    {
                        "attacker": attacker.name,
                        "attacker_slot": slot_label,
                        "move": move_name,
                        "priority": prio,
                        "vs_slot": our_key,
                        "target": defender.name,
                        "dmg_pct": [est["dmg_pct_min"], est["dmg_pct_max"]],
                        "ko_chance": est["ko_chance"],
                        "note": (
                            f"{attacker.name} {move_name} (prio +{prio}) can move "
                            f"before speed order vs {defender.name}"
                        ),
                    }
                )
    # Prefer KO-capable priority first, then higher priority, then damage.
    rank = {"guaranteed": 0, "likely": 1, "chip": 2, "low": 3}
    threats.sort(
        key=lambda t: (
            rank.get(t["ko_chance"], 9),
            -t["priority"],
            -(t["dmg_pct"][1] if t.get("dmg_pct") else 0),
        )
    )
    return threats[:12]


def build_protect_status(battle) -> dict:
    """Track consecutive Protect risk per user slot."""
    out = {}
    for key, slot in (("slot_a", battle.user.slot_a), ("slot_b", battle.user.slot_b)):
        active = slot.active
        if not _alive(active):
            out[key] = {"active": None, "protect_streak": 0, "consecutive_protect_risky": False}
            continue
        streak = _protect_level(active)
        out[key] = {
            "active": active.name,
            "protect_streak": streak,
            "consecutive_protect_risky": streak >= 1,
            "note": (
                "Protect used recently — consecutive Protect may fail; prefer attack."
                if streak >= 1
                else "Protect available."
            ),
        }
    return out


def infer_opponent_pokemon(pkmn) -> dict | None:
    if not pkmn or not pkmn.name or pkmn.name == "none":
        return None
    key = normalize_name(pkmn.name)
    base = _species(pkmn)
    template = OPPONENT_SETS.get(key) or OPPONENT_SETS.get(base)
    revealed_moves = [m.name for m in (pkmn.moves or [])]
    if not template:
        return {
            "name": pkmn.name,
            "ability": pkmn.ability,
            "item": pkmn.item if pkmn.item != constants.UNKNOWN_ITEM else None,
            "revealed_moves": revealed_moves,
            "likely_moves": revealed_moves,
            "threat": "Unknown set — play around common STAB and Protect.",
        }
    return {
        "name": pkmn.name,
        "ability": pkmn.ability or template.get("ability"),
        "item": (
            pkmn.item
            if pkmn.item and pkmn.item != constants.UNKNOWN_ITEM
            else (template.get("items") or [None])[0]
        ),
        "likely_items": template.get("items", []),
        "revealed_moves": revealed_moves,
        "likely_moves": sorted(set(revealed_moves) | set(template.get("moves", []))),
        "threat": template.get("threat", ""),
    }


def build_opponent_inferences(battle) -> dict:
    out = {
        "active": [],
        "bench": [],
        "tags": [],
    }
    tags = set()
    for slot in (battle.opponent.slot_a, battle.opponent.slot_b):
        if _alive(slot.active):
            info = infer_opponent_pokemon(slot.active)
            if info:
                out["active"].append(info)
            key = _species(slot.active)
            if key in _FAKEOUT:
                tags.add("fake_out")
            if key in _TR_SETTERS:
                tags.add("trick_room")
            if key in _SUN or key in _CHLOROPHYLL:
                tags.add("sun")
            if key in _RAIN:
                tags.add("rain")
            if key in _SHADOW_TAG:
                tags.add("shadow_tag")
    for p in battle.opponent.reserve:
        if not p.name or p.name == "none":
            continue
        info = infer_opponent_pokemon(p)
        if info:
            out["bench"].append(info)
        key = _species(p)
        if key in _FAKEOUT:
            tags.add("fake_out")
        if key in _TR_SETTERS:
            tags.add("trick_room")
        if key in _SUN or key in _CHLOROPHYLL:
            tags.add("sun")
        if key in _RAIN:
            tags.add("rain")
        if key in _SHADOW_TAG:
            tags.add("shadow_tag")
    if any(
        _move_priority(m, battle) > 0
        for info in out["active"]
        for m in (info.get("likely_moves") or [])
    ):
        tags.add("priority")
    out["tags"] = sorted(tags)
    return out


def build_team_roles(battle) -> dict:
    roles = {}
    seen = set()
    for p in [
        battle.user.slot_a.active,
        battle.user.slot_b.active,
        *list(battle.user.reserve),
    ]:
        if not p or not p.name or p.name == "none":
            continue
        key = normalize_name(p.name)
        base = _species(p)
        if key in seen and base in seen:
            continue
        role = TEAM_ROLES.get(key) or TEAM_ROLES.get(base)
        if role:
            roles[p.name] = role
            seen.add(key)
            seen.add(base)
    return roles


def contextual_meta_hints(battle) -> list[str]:
    hints = list(BASE_META_HINTS)
    opp_keys = set()
    for slot in (battle.opponent.slot_a, battle.opponent.slot_b):
        if slot.active and slot.active.name:
            opp_keys.add(_species(slot.active))
            opp_keys.add(normalize_name(slot.active.name))
    for p in battle.opponent.reserve:
        if p.name and p.name != "none":
            opp_keys.add(_species(p))
            opp_keys.add(normalize_name(p.name))

    if opp_keys & _FAKEOUT:
        hints.append("Opponent has Fake Out — Protect or switch the threatened slot on T1.")
    if opp_keys & _TR_SETTERS:
        hints.append("Opponent can set Trick Room — Encore / KO the setter or lead Kingambit.")
    if opp_keys & _SHADOW_TAG:
        hints.append("Shadow Tag risk — bring spread damage and do not soft-lock into Perish.")
    if opp_keys & _SUN or opp_keys & _CHLOROPHYLL:
        hints.append("Sun/Chlorophyll — Sleep Powder / Eruption possible; Protect Zard or remove sun.")
    if opp_keys & _RAIN:
        hints.append("Rain team — Mega Y Drought contests weather; avoid Water-weak leads.")
    if getattr(battle, "weather", None) == constants.SUN:
        hints.append("Sun is up — prefer Fire Weather Ball / Heat Wave; watch Chlorophyll speed.")
    if battle.user.side_conditions.get(constants.TAILWIND):
        hints.append("Your Tailwind is active — capitalize with offense; do not re-Tailwind.")
    if getattr(battle, "trick_room", False):
        hints.append("Trick Room is up — prefer Kingambit / slow attackers; avoid Tailwind.")

    prio = build_priority_threats(battle)
    ko_prio = [t for t in prio if t.get("ko_chance") in ("guaranteed", "likely")]
    if ko_prio:
        t = ko_prio[0]
        hints.append(
            f"PRIORITY KO THREAT: {t['attacker']} {t['move']} can KO {t['target']} "
            f"before speed order — Protect or don't attack into it."
        )
    elif prio:
        t = prio[0]
        hints.append(
            f"Priority threat: {t['attacker']} {t['move']} (+{t['priority']}) vs "
            f"{t['target']} — speed order alone is not safe."
        )

    protect = build_protect_status(battle)
    for key, st in protect.items():
        if st.get("consecutive_protect_risky"):
            hints.append(
                f"{key} ({st.get('active')}): consecutive Protect risky — attack instead."
            )

    living = _living_user_count(battle)
    if living <= 2:
        hints.append(
            f"Endgame ({living} mon(s) left): prioritize KO / Protect; no bench switches."
        )
        if ko_prio:
            hints.append(
                "1vX rule: if foe priority can KO you, Protect; only attack if you "
                "survive their priority or also have priority into a KO."
            )
    return hints


def build_turn_plan_hints(battle) -> list[str]:
    """Short 1–2 turn plan suggestions from damage matrix + field state."""
    plans = []
    dmg = build_damage_ko_matrix(battle)
    incoming = build_incoming_ko_matrix(battle)
    tw = bool(battle.user.side_conditions.get(constants.TAILWIND))
    sun = getattr(battle, "weather", None) == constants.SUN

    for t in build_priority_threats(battle)[:3]:
        pct = t.get("dmg_pct") or ["?", "?"]
        plans.append(
            f"PRIORITY: {t['attacker']} {t['move']} vs {t['target']}: "
            f"{t['ko_chance']} ({pct[0]}-{pct[1]}%) — check before attacking"
        )

    for attacker_name, moves in incoming.items():
        for move_name, targets in moves.items():
            for our_key, est in targets.items():
                if est.get("ko_chance") in ("guaranteed", "likely"):
                    pct = est.get("dmg_pct") or ["?", "?"]
                    prio = est.get("priority") or 0
                    tag = f" prio+{prio}" if prio > 0 else ""
                    plans.append(
                        f"INCOMING{tag}: {attacker_name} {move_name} vs {our_key}: "
                        f"{est['ko_chance']} ({pct[0]}-{pct[1]}%)"
                    )

    for attacker_name, moves in dmg.items():
        for move_name, targets in moves.items():
            for foe_key, est in targets.items():
                if est.get("ko_chance") in ("guaranteed", "likely"):
                    pct = est.get("dmg_pct") or ["?", "?"]
                    plans.append(
                        f"{attacker_name} {move_name} vs {foe_key}: {est['ko_chance']} "
                        f"({pct[0]}-{pct[1]}%)"
                    )

    for slot, label in (
        (battle.user.slot_a, "slot_a"),
        (battle.user.slot_b, "slot_b"),
    ):
        active = slot.active
        if not _alive(active):
            continue
        key = _species(active)
        if key == "whimsicott" and not tw and not battle.trick_room:
            plans.append(f"{label}: set Tailwind before committing fragile offense.")
        if key == "charizard" and getattr(active, "can_mega_evo", False):
            plans.append(
                f"{label}: Mega Y this turn for Drought; prefer Weather Ball into KO range."
            )
        if key in ("charizard", "charizardmegay") and sun:
            plans.append(f"{label}: sun-boosted Heat Wave / Weather Ball.")
        if key == "kingambit":
            plans.append(
                f"{label}: if slower than foes, Protect or Sucker Punch into attack."
            )
        if _protect_level(active) >= 1:
            plans.append(f"{label}: consecutive Protect risky — prefer offense.")

    seen = set()
    out = []
    for p in plans:
        if p not in seen:
            seen.add(p)
            out.append(p)
        if len(out) >= 10:
            break
    return out


def _index_for(user, species: str):
    species = normalize_name(species)
    for slot in (user.slot_a, user.slot_b):
        p = slot.active
        if p and p.name and p.name != "none":
            if normalize_name(p.name) == species or _species(p) == species:
                return p.index
    for p in user.reserve:
        if p.name and p.name != "none":
            if normalize_name(p.name) == species or _species(p) == species:
                return p.index
    return None


def _all_user_mons(user):
    mons = []
    for slot in (user.slot_a, user.slot_b):
        if slot.active and slot.active.name and slot.active.name != "none":
            mons.append(slot.active)
    for p in user.reserve:
        if p.name and p.name != "none":
            mons.append(p)
    return mons


def recommend_team_preview(battle) -> dict:
    """
    Return recommended lead order for current sample team vs opponent preview.
    digits: lead_a, lead_b, reserve_1, reserve_2
    """
    opp = set()
    for p in battle.opponent.reserve:
        if p.name and p.name != "none":
            opp.add(_species(p))
            opp.add(normalize_name(p.name))
    for slot in (battle.opponent.slot_a, battle.opponent.slot_b):
        if slot.active and slot.active.name:
            opp.add(_species(slot.active))
            opp.add(normalize_name(slot.active.name))

    has_tr = bool(opp & _TR_SETTERS)
    has_fakeout = bool(opp & _FAKEOUT)
    has_sun = bool(opp & (_SUN | _CHLOROPHYLL))
    has_rain = bool(opp & _RAIN)
    has_shadow = bool(opp & _SHADOW_TAG)
    has_dragons = bool(
        opp
        & {
            "archaludon",
            "kommoo",
            "hydreigon",
            "garchomp",
            "dragonite",
            "latias",
            "latios",
            "goodra",
            "goodrahisui",
            "dragapult",
        }
    )

    # Prefer species that exist on our current team.
    if has_tr:
        order = ("whimsicott", "kingambit", "charizard", "garchomp")
        reason = "TR: Whimsicott Encore/Tailwind + Kingambit; Zard/Chomp back."
    elif has_shadow:
        order = ("whimsicott", "garchomp", "charizard", "kingambit")
        reason = "Shadow Tag: Tailwind + Rock Slide/EQ pressure; avoid soft Perish."
    elif has_sun:
        order = ("whimsicott", "garchomp", "kingambit", "basculegion")
        reason = "Enemy sun/Chlorophyll: lead Tailwind+Chomp; keep Zard in back."
    elif has_rain:
        order = ("whimsicott", "charizard", "garchomp", "kingambit")
        reason = "Rain: contest with Mega Y Drought behind Tailwind."
    elif has_fakeout:
        order = ("whimsicott", "garchomp", "charizard", "kingambit")
        reason = "Fake Out: Tailwind first; Protect Chomp or click Rock Slide."
    elif has_dragons:
        order = ("floetteeternal", "whimsicott", "garchomp", "charizard")
        if _index_for(battle.user, "floetteeternal") is None:
            order = ("whimsicott", "kingambit", "garchomp", "charizard")
        reason = "Dragons: Fairy pressure + Tailwind."
    else:
        order = ("whimsicott", "garchomp", "charizard", "kingambit")
        reason = "Default: Tailwind lead + Life Orb Chomp; Zard/Gambit back."

    digits = []
    for species in order:
        idx = _index_for(battle.user, species)
        if idx is not None and str(idx) not in digits:
            digits.append(str(idx))
    if len(digits) < 4:
        for p in sorted(_all_user_mons(battle.user), key=lambda x: x.index or 99):
            if str(p.index) not in digits:
                digits.append(str(p.index))
            if len(digits) == 4:
                break

    return {
        "digits": "".join(digits[:4]),
        "order_species": list(order),
        "reason": reason,
        "opponent_tags": sorted(
            t
            for t, flag in (
                ("trick_room", has_tr),
                ("fake_out", has_fakeout),
                ("sun", has_sun),
                ("rain", has_rain),
                ("shadow_tag", has_shadow),
                ("dragons", has_dragons),
            )
            if flag
        ),
    }
