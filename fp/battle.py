from collections import defaultdict
from collections import namedtuple
from dataclasses import dataclass

import constants
import logging
from config import FoulPlayConfig

from data import all_move_json
from data import pokedex

from fp.helpers import get_pokemon_info_from_condition
from fp.helpers import normalize_name
from fp.helpers import calculate_stats

from fp.helpers import POKEMON_TYPE_INDICES
from teams.team_converter import packed_to_dict

logger = logging.getLogger(__name__)


LastUsedMove = namedtuple("LastUsedMove", ["pokemon_name", "move", "turn"])


# Based on the format, this dict controls which pokemon will be replaced during team preview
# Some pokemon's forms are not revealed in team preview
smart_team_preview = {
    "gen8ou": {
        "urshifu": "urshifurapidstrike"  # urshifu banned in gen8ou
    },
    "gen9battlefactory": {
        "zacian": "zaciancrowned"  # only zaciancrowned is used in gen9battlefactory
    },
}


boost_multiplier_lookup = {
    -6: 2 / 8,
    -5: 2 / 7,
    -4: 2 / 6,
    -3: 2 / 5,
    -2: 2 / 4,
    -1: 2 / 3,
    0: 2 / 2,
    1: 3 / 2,
    2: 4 / 2,
    3: 5 / 2,
    4: 6 / 2,
    5: 7 / 2,
    6: 8 / 2,
}


@dataclass
class StatRange:
    min: int | float
    max: int | float


class Battle:
    def __init__(self, battle_tag):
        self.battle_tag = battle_tag
        self.user = Battler("1")
        self.opponent = Battler("2")
        self.weather = None
        self.weather_turns_remaining = -1
        self.weather_source = ""
        self.field = None
        self.field_turns_remaining = 0
        self.trick_room = False
        self.trick_room_turns_remaining = 0
        self.gravity = False
        self.team_preview = False

        self.turn = False

        self.started = False
        self.rqid = None

        self.force_switch = (False, False)  # (slot_a, slot_b)
        self.wait = False

        self.battle_type = None
        self.generation = None
        self.time_remaining = None

        self.request_json = None
        self.msg_list = []

    def during_team_preview(self): ...

    def start_non_team_preview_battle(self, user_json, opponent_switch_string):
        self.user.initialize_first_turn_user_from_json(user_json)

        pkmn_information = opponent_switch_string.split("|")[3]
        pkmn = Pokemon.from_switch_string(pkmn_information)
        self.opponent.active = pkmn

        self.started = True
        self.rqid = user_json[constants.RQID]

    def mega_evolve_possible(self):
        return (
            any(g in self.generation for g in constants.MEGA_EVOLVE_GENERATIONS)
            or "nationaldex" in FoulPlayConfig.pokemon_format
        )

    def get_effective_speed(self, battler):
        boosted_speed = battler.active.calculate_boosted_stats()[constants.SPEED]

        if self.weather == constants.SUN and battler.active.ability == "chlorophyll":
            boosted_speed *= 2
        elif self.weather == constants.RAIN and battler.active.ability == "swiftswim":
            boosted_speed *= 2
        elif self.weather == constants.SAND and battler.active.ability == "sandrush":
            boosted_speed *= 2
        elif (
            self.weather in constants.HAIL_OR_SNOW
            and battler.active.ability == "slushrush"
        ):
            boosted_speed *= 2

        if (
            self.field == constants.ELECTRIC_TERRAIN
            and battler.active.ability == "surgesurfer"
        ):
            boosted_speed *= 2

        if battler.active.ability == "unburden" and not battler.active.item:
            boosted_speed *= 2
        elif (
            battler.active.ability == "quickfeet" and battler.active.status is not None
        ):
            boosted_speed *= 1.5

        if battler.side_conditions[constants.TAILWIND]:
            boosted_speed *= 2

        if "choicescarf" == battler.active.item:
            boosted_speed *= 1.5

        if (
            constants.PARALYZED == battler.active.status
            and battler.active.ability != "quickfeet"
        ):
            boosted_speed *= 0.5

        if any(
            vs in battler.active.volatile_statuses
            for vs in ["quarkdrivespe", "protosynthesisspe"]
        ):
            boosted_speed *= 1.5

        return int(boosted_speed)

    def neutralizing_gas_is_active(self):
        return (
            (
                self.user.slot_a.active is not None
                and self.user.slot_a.active.ability == "neutralizinggas"
            )
            or (
                self.user.slot_b.active is not None
                and self.user.slot_b.active.ability == "neutralizinggas"
            )
            or (
                self.opponent.slot_a.active is not None
                and self.opponent.slot_a.active.ability == "neutralizinggas"
            )
            or (
                self.opponent.slot_b.active is not None
                and self.opponent.slot_b.active.ability == "neutralizinggas"
            )
        )

    def find_best_move(self):
        raise NotImplementedError("find_best_move must be implemented in subclasses")


class Slot:
    def __init__(self, identifier: str):
        self.identifier = identifier
        self.active = None
        self.trapped = False
        self.baton_passing = False
        self.shed_tailing = False
        self.wish = (0, 0)
        self.future_sight = (0, "")

        # last_selected_move: The last move that was selected (Bot only)
        # last_used_move: The last move that was observed publicly (Bot and Opponent)
        # they may seem the same, but `last_selected_move` is important in situations where the bot selects
        #   a move but gets knocked out before it can use it
        self.last_selected_move = LastUsedMove("", "", 0)
        self.last_used_move = LastUsedMove("", "", 0)

    def lock_active_pkmn_first_turn_moves(self):
        # disable firstimpression and fakeout if the last_used_move was not a switch
        if self.last_used_move.pokemon_name == self.active.name:
            for m in self.active.moves:
                if m.name in constants.FIRST_TURN_MOVES:
                    m.disabled = True

    def lock_active_pkmn_status_moves_if_active_has_assaultvest(self):
        if self.active.item == "assaultvest":
            for m in self.active.moves:
                if all_move_json[m.name][constants.CATEGORY] == constants.STATUS:
                    m.disabled = True

    def choice_lock_moves(self):
        # if the active pokemon has a choice item and their last used move was by this pokemon -> lock their other moves
        #
        # known bug: the bot tricking a choice item onto the opponent will lock their move when it shouldn't.
        # this will only happen if the bot tricks the opponent after the opponent has already used a move
        if (
            self.active.item in constants.CHOICE_ITEMS
            and self.last_used_move.pokemon_name == self.active.name
            and self.last_used_move.move not in ["trick", "switcheroo"]
        ):
            for m in self.active.moves:
                if (
                    self.last_used_move.move == constants.HIDDEN_POWER
                    and m.name.startswith(constants.HIDDEN_POWER)
                ):
                    pass
                elif m.name != self.last_used_move.move:
                    m.disabled = True

    def taunt_lock_moves(self):
        if constants.TAUNT in self.active.volatile_statuses:
            for m in self.active.moves:
                if all_move_json[m.name][constants.CATEGORY] == constants.STATUS:
                    m.disabled = True

    def locked_move_lock(self):
        if constants.LOCKED_MOVE in self.active.volatile_statuses:
            for m in self.active.moves:
                if m.name != self.last_used_move.move:
                    m.disabled = True

    def lock_moves(self):
        self.choice_lock_moves()
        self.lock_active_pkmn_status_moves_if_active_has_assaultvest()
        self.lock_active_pkmn_first_turn_moves()
        self.taunt_lock_moves()
        self.locked_move_lock()

    def initialize_user_active_from_request_json(
        self, request_json: dict, active_index: int
    ):
        my_active_pkmn = request_json[constants.ACTIVE][active_index]

        self.active.can_mega_evo = my_active_pkmn.get(constants.CAN_MEGA_EVO, False)
        self.active.can_ultra_burst = my_active_pkmn.get(
            constants.CAN_ULTRA_BURST, False
        )
        self.active.can_dynamax = my_active_pkmn.get(constants.CAN_DYNAMAX, False)
        self.active.can_terastallize = my_active_pkmn.get(
            constants.CAN_TERASTALLIZE, False
        )

        # request JSON gives detailed information about the moves
        # available to the active pkmn. Take those as the source of truth
        self.active.moves.clear()
        for index, move in enumerate(my_active_pkmn[constants.MOVES]):
            # hidden power's ID is always 'hiddenpower' regardless of the type
            # parse it separately from the 'move' key
            if move[constants.ID] == constants.HIDDEN_POWER:
                self.active.add_move(normalize_name(move["move"]))
            else:
                self.active.add_move(move[constants.ID])
            self.active.moves[-1].disabled = move.get(constants.DISABLED, False)
            self.active.moves[-1].current_pp = move.get(constants.PP, 1)

            # PokemonShowdown disables these moves in the protocol after they are used once,
            # but poke-engine does not expect them to be disabled
            # poke-engine deals with this by not allowing these moves to be selected if they are the last used move
            if self.last_used_move.move in ["gigatonhammer", "bloodmoon"]:
                for m in self.active.moves:
                    if m.name == self.last_used_move.move and m.disabled:
                        m.disabled = False

            try:
                self.active.moves[index].can_z = my_active_pkmn[constants.CAN_Z_MOVE][
                    index
                ]
            except KeyError:
                pass

    def re_initialize_active_pokemon_from_request_json(self, request_json):
        """
        Re-initializes the active pokemon based on the last request JSON that was received
        This is useful when the bot's active pkmn has mega-evolved. We need to get the new stats/hp
        """
        pokedex_name = normalize_name(pokedex[self.active.name][constants.NAME])
        request_json_active_pkmn = [
            p
            for p in request_json["side"]["pokemon"]
            if normalize_name(p[constants.DETAILS]).split(",")[0] == pokedex_name
            or normalize_name(p[constants.DETAILS]).split(",")[0]
            == self.active.base_name
        ]
        if pokedex_name == "terapagosstellar" and len(request_json_active_pkmn) == 0:
            request_json_active_pkmn = [
                p
                for p in request_json["side"]["pokemon"]
                if normalize_name(p[constants.DETAILS]).split(",")[0]
                == "terapagosterastal"
                or normalize_name(p[constants.DETAILS]).split(",")[0]
                == self.active.base_name
            ]
        assert (
            len(request_json_active_pkmn) == 1
        ), f"Didn't find exactly 1 {pokedex_name}, pokemon: {request_json}"
        pkmn_info = request_json_active_pkmn[0]
        for stat, number in pkmn_info[constants.STATS].items():
            self.active.stats[constants.STAT_ABBREVIATION_LOOKUPS[stat]] = number
        self.active.hp, _, _ = get_pokemon_info_from_condition(
            pkmn_info[constants.CONDITION]
        )


class Battler:
    def __init__(self, identifier: str):
        self.identifier = identifier
        self.account_name = None
        self.slot_a = Slot("a")
        self.slot_b = Slot("b")
        self.name = None
        self.reserve = []
        self.side_conditions = defaultdict(lambda: 0)

    def from_packed_string(self, packed_string: str):
        team_dict = packed_to_dict(packed_string)
        for pkmn in team_dict:
            p = Pokemon(pkmn["name"], pkmn["level"])
            p.ability = pkmn["ability"]
            p.item = pkmn["item"]
            p.tera_type = pkmn["tera_type"]
            for mv in pkmn["moves"]:
                p.add_move(mv)
            self.reserve.append(p)

    def from_team_preview_species(self, switch_strings: list):
        """
        Build the reserve from team-preview `|poke|` detail strings
        (e.g. "Azumarill, L50, F"). Used when a full team sheet is not
        available (e.g. Open Team Sheets was not accepted). Only the species
        and level are known; movesets/items/abilities are predicted/revealed
        as the battle progresses.
        """
        for switch_string in switch_strings:
            self.reserve.append(Pokemon.from_switch_string(switch_string))

    def get_slot(self, slot_name: str):
        if slot_name == "a":
            return self.slot_a
        elif slot_name == "b":
            return self.slot_b
        else:
            raise ValueError("Invalid slot name: {}".format(slot_name))

    def num_fainted_pkmn(self):
        num_fainted = 0
        for pkmn in self.reserve + [self.slot_a.active, self.slot_b.active]:
            if not pkmn.is_alive():
                num_fainted += 1

        return num_fainted

    def mega_revealed(self):
        return (
            self.slot_a.active.is_mega
            or self.slot_b.active.is_mega
            or any(p.is_mega for p in self.reserve)
        )

    def find_pokemon_in_reserves(self, pkmn_name):
        for reserve_pkmn in self.reserve:
            if reserve_pkmn.name == pkmn_name or reserve_pkmn.base_name == pkmn_name:
                return reserve_pkmn
        return None

    def find_reserve_pkmn_by_unknown_forme(self, pkmn_name):
        for reserve_pkmn in filter(lambda x: x.unknown_forme, self.reserve):
            pkmn_base_forme = normalize_name(pokedex[pkmn_name].get("changesFrom", ""))
            if pkmn_base_forme == reserve_pkmn.base_name:
                return reserve_pkmn
        return None

    def find_reserve_pokemon_by_nickname(self, pkmn_nickname):
        for reserve_pkmn in self.reserve:
            if pkmn_nickname == reserve_pkmn.nickname:
                return reserve_pkmn
        return None

    def find_pkmn_by_index(self, index):
        if self.slot_a.active is not None and self.slot_a.active.index == index:
            return self.slot_a.active
        elif self.slot_b.active is not None and self.slot_b.active.index == index:
            return self.slot_b.active
        for reserve_pkmn in self.reserve:
            if reserve_pkmn.index == index:
                return reserve_pkmn

        debug_info = [(p.name, p.index) for p in self.reserve]
        debug_info.insert(0, (self.slot_a.active.name, self.slot_a.active.index))
        debug_info.insert(0, (self.slot_b.active.name, self.slot_b.active.index))
        raise ValueError(
            "No pokemon found with index {}, reserves: {}".format(index, debug_info)
        )

    def update_from_request_json(self, request_json):
        """
        Updates the battler's information based on the request JSON
        This should be called with a cloned battle/battler so that the original is not modified
        """
        try:
            trapped = request_json[constants.ACTIVE][0].get(constants.TRAPPED, False)
            maybe_trapped = request_json[constants.ACTIVE][0].get(
                constants.MAYBE_TRAPPED, False
            )
            self.slot_a.trapped = trapped or maybe_trapped
        except KeyError:
            self.slot_a.trapped = False
        try:
            trapped = request_json[constants.ACTIVE][1].get(constants.TRAPPED, False)
            maybe_trapped = request_json[constants.ACTIVE][1].get(
                constants.MAYBE_TRAPPED, False
            )
            self.slot_b.trapped = trapped or maybe_trapped
        except KeyError:
            self.slot_b.trapped = False

        for index, pkmn_dict in enumerate(
            request_json[constants.SIDE][constants.POKEMON]
        ):
            switch_string_pkmn = Pokemon.from_switch_string(
                pkmn_dict[constants.DETAILS]
            )
            pkmn_name = switch_string_pkmn.name
            pkmn_level = switch_string_pkmn.level
            pkmn_status = switch_string_pkmn.status
            if pkmn_dict[constants.ACTIVE]:
                if (
                    self.slot_a.active.name != pkmn_name
                    and self.slot_a.active.base_name != pkmn_name
                    and self.slot_b.active.name != pkmn_name
                    and self.slot_b.active.base_name != pkmn_name
                ):
                    raise ValueError(
                        "Active pokemon mismatch: expected {}, {}, {}, or {}. Got {}".format(
                            self.slot_a.active.name,
                            self.slot_a.active.base_name,
                            self.slot_b.active.name,
                            self.slot_b.active.base_name,
                            pkmn_name,
                        )
                    )

                if constants.ACTIVE in request_json:
                    self.slot_a.initialize_user_active_from_request_json(
                        request_json, 0
                    )
                    self.slot_b.initialize_user_active_from_request_json(
                        request_json, 1
                    )

                if (
                    self.slot_a.active.name == pkmn_name
                    or self.slot_a.active.base_name == pkmn_name
                ):
                    pkmn = self.slot_a.active
                elif (
                    self.slot_b.active.name == pkmn_name
                    or self.slot_b.active.base_name == pkmn_name
                ):
                    pkmn = self.slot_b.active
                else:
                    raise ValueError("Pkmn is not in either slot: {}".format(pkmn_name))
            else:
                pkmn = self.find_pokemon_in_reserves(pkmn_name)
                for move_name in pkmn_dict[constants.MOVES]:
                    if not pkmn.get_move(move_name):
                        pkmn.add_move(move_name)

            pkmn.index = index + 1
            pkmn.level = pkmn_level
            pkmn.status = pkmn_status
            pkmn.nickname = Pokemon.extract_nickname_from_pokemonshowdown_string(
                pkmn_dict[constants.IDENT]
            )
            pkmn.reviving = pkmn_dict.get(constants.REVIVING, False)
            pkmn.hp, pkmn.max_hp, pkmn.status = get_pokemon_info_from_condition(
                pkmn_dict[constants.CONDITION]
            )
            pkmn.ability = pkmn_dict[constants.REQUEST_DICT_ABILITY]
            pkmn.item = pkmn_dict[constants.ITEM] if pkmn_dict[constants.ITEM] else None
            for stat, number in pkmn_dict[constants.STATS].items():
                pkmn.stats[constants.STAT_ABBREVIATION_LOOKUPS[stat]] = number

    def initialize_first_turn_user_from_json(self, request_json):
        """
        Similar to `update_from_request_json`, but meant to be used on the first `request_json` that is seen
        This function differs in that it adds new pokemon to the Side rather than modifying existing ones
        """
        try:
            trapped = request_json[constants.ACTIVE][0].get(constants.TRAPPED, False)
            maybe_trapped = request_json[constants.ACTIVE][0].get(
                constants.MAYBE_TRAPPED, False
            )
            self.slot_a.trapped = trapped or maybe_trapped
        except KeyError:
            self.slot_a.trapped = False
        try:
            trapped = request_json[constants.ACTIVE][1].get(constants.TRAPPED, False)
            maybe_trapped = request_json[constants.ACTIVE][1].get(
                constants.MAYBE_TRAPPED, False
            )
            self.slot_b.trapped = trapped or maybe_trapped
        except KeyError:
            self.slot_b.trapped = False

        self.name = request_json[constants.SIDE][constants.ID]
        self.reserve.clear()
        for index, pkmn_dict in enumerate(
            request_json[constants.SIDE][constants.POKEMON]
        ):
            nickname = pkmn_dict[constants.IDENT]
            pkmn_details = pkmn_dict[constants.DETAILS]
            pkmn_item = pkmn_dict[constants.ITEM] if pkmn_dict[constants.ITEM] else None
            pkmn = Pokemon.from_switch_string(pkmn_details, nickname=nickname)

            # For some reason PS sends "zacian" during team preview
            # when you have a zacian with a rusted sword
            if pkmn.name.startswith("zacian") and pkmn_item == "rustedsword":
                pkmn = Pokemon("zaciancrowned", pkmn.level)
                pkmn.nickname = nickname
            elif pkmn.name.startswith("zamazenta") and pkmn_item == "rustedshield":
                pkmn = Pokemon("zamazentacrowned", pkmn.level)
                pkmn.nickname = nickname

            pkmn.ability = pkmn_dict[constants.REQUEST_DICT_ABILITY]
            pkmn.index = index + 1
            pkmn.reviving = pkmn_dict.get(constants.REVIVING, False)
            pkmn.hp, pkmn.max_hp, pkmn.status = get_pokemon_info_from_condition(
                pkmn_dict[constants.CONDITION]
            )
            for stat, number in pkmn_dict[constants.STATS].items():
                pkmn.stats[constants.STAT_ABBREVIATION_LOOKUPS[stat]] = number

            pkmn.item = pkmn_item
            if constants.TERA_TYPE in pkmn_dict:
                pkmn.tera_type = normalize_name(pkmn_dict[constants.TERA_TYPE])

            if pkmn_dict[constants.ACTIVE]:
                if index == 0:
                    self.slot_a.active = pkmn
                elif index == 1:
                    self.slot_b.active = pkmn
                else:
                    raise ValueError(
                        "Unexpected active pokemon index when trying to assign active: {}".format(
                            index
                        )
                    )
            else:
                self.reserve.append(pkmn)

            for move_name in pkmn_dict[constants.MOVES]:
                if (
                    pkmn.name.startswith("zacian")
                    and pkmn_item == "rustedsword"
                    and move_name == "ironhead"
                ):
                    logger.info(
                        "Zacian with rusted sword: changing ironhead to behemothblade"
                    )
                    move_name = "behemothblade"
                elif (
                    pkmn.name.startswith("zamazenta")
                    and pkmn_item == "rustedshield"
                    and move_name == "ironhead"
                ):
                    logger.info(
                        "Zamazenta with rusted shield: changing ironhead to behemothbash"
                    )
                    move_name = "behemothbash"
                pkmn.add_move(move_name)

        # if there is no active pokemon, we do not want to look through it's moves
        if constants.ACTIVE not in request_json:
            return

        self.slot_a.initialize_user_active_from_request_json(request_json, 0)
        self.slot_b.initialize_user_active_from_request_json(request_json, 1)


class Pokemon:
    def __init__(
        self, name: str, level: int, nature="serious", evs=(85,) * 6, ivs=(31,) * 6
    ):
        self.name = normalize_name(name)
        self.nickname = None
        self.base_name = self.name
        self.level = level
        self.nature = nature
        self.evs = evs
        self.speed_range = StatRange(min=0, max=float("inf"))
        self.hidden_power_possibilities = set(POKEMON_TYPE_INDICES.keys())
        self.revealed = False
        self.stellar_boosted_types = []

        try:
            self.base_stats = pokedex[self.name][constants.BASESTATS]
        except KeyError:
            logger.info("Could not pokedex entry for {}".format(self.name))
            self.name = [k for k in pokedex if self.name.startswith(k)][0]
            logger.info("Using {} instead".format(self.name))
            self.base_stats = pokedex[self.name][constants.BASESTATS]

        self.stats = calculate_stats(
            self.base_stats, self.level, nature=nature, evs=evs, ivs=ivs
        )

        self.max_hp = self.stats.pop(constants.HITPOINTS)
        self.hp = self.max_hp
        self.substitute_hit = False
        if self.name == "shedinja":
            self.max_hp = 1
            self.hp = 1

        self.ability = None
        self.types = pokedex[self.name][constants.TYPES]
        self.item = constants.UNKNOWN_ITEM
        self.removed_item = None
        self.unknown_forme = False

        self.moves_used_since_switch_in = set()
        self.zoroark_disguised_as = None
        self.hp_at_switch_in = self.max_hp
        self.status_at_switch_in = None
        self.terastallized = False
        self.tera_type = None
        self.times_attacked = 0
        self.original_ability = None
        self.fainted = False
        self.reviving = False
        self.moves = []
        self.status = None
        self.volatile_statuses = []
        self.volatile_status_durations = defaultdict(lambda: 0)
        self.boosts = defaultdict(lambda: 0)
        self.rest_turns = 0
        self.sleep_turns = 0
        self.knocked_off = False
        self.can_mega_evo = False
        self.can_ultra_burst = False
        self.can_dynamax = False
        self.can_terastallize = False
        self.is_mega = False
        self.can_have_choice_item = True
        self.item_inferred = False
        self.gen_3_consecutive_sleep_talks = 0
        self.impossible_items = set()
        self.impossible_abilities = set()

    @classmethod
    def from_dict(cls, pkmn_dict: dict, level=50):
        evs = []
        for ev in pkmn_dict["evs"].values():
            if ev:
                evs.append(int(ev))
            else:
                evs.append(0)
        ivs = []
        for iv in pkmn_dict["ivs"].values():
            if iv:
                ivs.append(int(iv))
            else:
                ivs.append(31)
        pkmn = cls(
            normalize_name(pkmn_dict["species"]),
            level,
            nature=pkmn_dict["nature"],
            evs=tuple(evs),
            ivs=tuple(ivs),
        )
        pkmn.ability = pkmn_dict[constants.ABILITY]
        pkmn.item = pkmn_dict[constants.ITEM]
        pkmn.tera_type = pkmn_dict["tera_type"]
        for move in pkmn_dict[constants.MOVES]:
            pkmn.add_move(move)
        return pkmn

    def has_type(self, pkmn_type: str):
        if self.terastallized and self.tera_type != "stellar":
            return pkmn_type == self.tera_type
        else:
            return pkmn_type in self.types

    def forme_change(self, new_forme_switch_string):
        current_hp_percentage = self.hp / self.max_hp

        new_pokemon = Pokemon.from_switch_string(new_forme_switch_string)
        self.name = new_pokemon.name
        self.hp = int(current_hp_percentage * self.max_hp)
        self.base_stats = new_pokemon.base_stats
        self.stats = calculate_stats(self.base_stats, self.level)
        self.types = new_pokemon.types

    def is_alive(self):
        return self.hp > 0

    def calculate_boosted_stats(self):
        return {
            constants.ATTACK: boost_multiplier_lookup[self.boosts[constants.ATTACK]]
            * self.stats[constants.ATTACK],
            constants.DEFENSE: boost_multiplier_lookup[self.boosts[constants.DEFENSE]]
            * self.stats[constants.DEFENSE],
            constants.SPECIAL_ATTACK: boost_multiplier_lookup[
                self.boosts[constants.SPECIAL_ATTACK]
            ]
            * self.stats[constants.SPECIAL_ATTACK],
            constants.SPECIAL_DEFENSE: boost_multiplier_lookup[
                self.boosts[constants.SPECIAL_DEFENSE]
            ]
            * self.stats[constants.SPECIAL_DEFENSE],
            constants.SPEED: boost_multiplier_lookup[self.boosts[constants.SPEED]]
            * self.stats[constants.SPEED],
        }

    @classmethod
    def extract_nickname_from_pokemonshowdown_string(cls, ps_string):
        return "".join(ps_string.split(":")[1:]).strip()

    @classmethod
    def from_switch_string(cls, switch_string, nickname=None):
        if nickname is not None:
            nickname = cls.extract_nickname_from_pokemonshowdown_string(nickname)

        details = switch_string.split(",")
        name = details[0]
        try:
            level = int(details[1].replace("L", "").strip())
        except (IndexError, ValueError):
            level = 100
        pkmn = Pokemon(name, level)
        pkmn.nickname = nickname
        return pkmn

    def set_spread(self, nature, evs):
        if isinstance(evs, str):
            evs = [int(e) for e in evs.split(",")]
        hp_percent = self.hp / self.max_hp
        self.stats = calculate_stats(
            self.base_stats, self.level, evs=evs, nature=nature
        )
        self.nature = nature
        self.evs = evs
        self.max_hp = self.stats.pop(constants.HITPOINTS)
        self.hp = round(self.max_hp * hp_percent)

    def add_move(self, move_name: str):
        try:
            new_move = Move(move_name)
            self.moves.append(new_move)
            return new_move
        except KeyError:
            logger.warning("{} is not a known move".format(move_name))
            return None

    def remove_move(self, move_name: str):
        for mv in self.moves:
            if mv.name == move_name:
                self.moves.remove(mv)
                return True
        return False

    def get_move(self, move_name: str):
        for m in self.moves:
            if m.name == normalize_name(move_name):
                return m
            elif m.name.startswith(constants.HIDDEN_POWER) and move_name.startswith(
                constants.HIDDEN_POWER
            ):
                return m
            elif m.name.startswith("return") and move_name.startswith("return"):
                return m
        return None

    @classmethod
    def get_dummy(cls):
        p = Pokemon("pikachu", 100)
        p.hp = 0
        p.name = ""
        p.ability = None
        p.fainted = True
        return p

    def __eq__(self, other):
        return self.name == other.name and self.level == other.level

    def __repr__(self):
        return "{}, level {}".format(self.name, self.level)


class Move:
    def __init__(self, name):
        name = normalize_name(name)
        if (
            constants.HIDDEN_POWER != name
            and constants.HIDDEN_POWER in name
            and not name.endswith(constants.HIDDEN_POWER_ACTIVE_MOVE_BASE_DAMAGE_STRING)
        ):
            name = "{}{}".format(
                name, constants.HIDDEN_POWER_ACTIVE_MOVE_BASE_DAMAGE_STRING
            )
        move_json = all_move_json[name]
        self.name = name
        self.max_pp = int(move_json.get(constants.PP) * 1.6)

        self.disabled = False
        self.can_z = False
        self.current_pp = self.max_pp

    def __eq__(self, other):
        return self.name == other.name

    def __repr__(self):
        return "{}".format(self.name)


@dataclass
class DamageDealt:
    attacker_side: Battler
    target_side: Battler
    attacker_slot: Slot
    target_slot: Slot
    move: str
    percent_damage: float
    crit: bool
    spread: bool
