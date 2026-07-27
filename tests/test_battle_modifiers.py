import unittest
import json

import constants
from fp.helpers import calculate_stats

from fp.battle import Battle
from fp.battle import Pokemon
from fp.battle import Move
from fp.battle import LastUsedMove
from fp.battle import boost_multiplier_lookup

from fp.battle_modifier import (
    request,
    fieldstart,
    fieldend,
    drag,
    clearboost,
    remove_item,
    sidestart,
    get_damage_dealt,
    faint,
)
from fp.battle_modifier import terastallize
from fp.battle_modifier import activate
from fp.battle_modifier import prepare
from fp.battle_modifier import switch_or_drag
from fp.battle_modifier import clearallboost
from fp.battle_modifier import heal_or_damage
from fp.battle_modifier import swapsideconditions
from fp.battle_modifier import move
from fp.battle_modifier import cant
from fp.battle_modifier import boost
from fp.battle_modifier import setboost
from fp.battle_modifier import unboost
from fp.battle_modifier import status
from fp.battle_modifier import weather
from fp.battle_modifier import curestatus
from fp.battle_modifier import start_volatile_status
from fp.battle_modifier import end_volatile_status
from fp.battle_modifier import update_ability
from fp.battle_modifier import form_change
from fp.battle_modifier import clearnegativeboost
from fp.battle_modifier import singleturn
from fp.battle_modifier import process_battle_updates
from fp.battle_modifier import upkeep
from fp.battle_modifier import inactive


# so we can instantiate a Battle object for testing
Battle.__abstractmethods__ = set()


class TestRequestMessage(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.slot_a.active = Pokemon("pikachu", 100)
        self.request_json = {
            "active": [
                {
                    "moves": [
                        {
                            "move": "Storm Throw",
                            "id": "stormthrow",
                            "pp": 16,
                            "maxpp": 16,
                            "target": "normal",
                            "disabled": False,
                        },
                        {
                            "move": "Ice Punch",
                            "id": "icepunch",
                            "pp": 24,
                            "maxpp": 24,
                            "target": "normal",
                            "disabled": False,
                        },
                        {
                            "move": "Bulk Up",
                            "id": "bulkup",
                            "pp": 32,
                            "maxpp": 32,
                            "target": "self",
                            "disabled": False,
                        },
                        {
                            "move": "Knock Off",
                            "id": "knockoff",
                            "pp": 32,
                            "maxpp": 32,
                            "target": "normal",
                            "disabled": False,
                        },
                    ]
                }
            ],
            "side": {
                "name": "NiceNameNerd",
                "id": "p1",
                "pokemon": [
                    {
                        "ident": "p1: Throh",
                        "details": "Throh, L83, M",
                        "condition": "335/335",
                        "active": True,
                        "stats": {
                            "atk": 214,
                            "def": 189,
                            "spa": 97,
                            "spd": 189,
                            "spe": 122,
                        },
                        "moves": ["stormthrow", "icepunch", "bulkup", "knockoff"],
                        "baseAbility": "moldbreaker",
                        "item": "leftovers",
                        "pokeball": "pokeball",
                        "ability": "moldbreaker",
                    },
                    {
                        "ident": "p1: Empoleon",
                        "details": "Empoleon, L77, F",
                        "condition": "256/256",
                        "active": False,
                        "stats": {
                            "atk": 137,
                            "def": 180,
                            "spa": 215,
                            "spd": 200,
                            "spe": 137,
                        },
                        "moves": ["icebeam", "grassknot", "scald", "flashcannon"],
                        "baseAbility": "torrent",
                        "item": "choicespecs",
                        "pokeball": "pokeball",
                        "ability": "torrent",
                    },
                    {
                        "ident": "p1: Emboar",
                        "details": "Emboar, L79, M",
                        "condition": "303/303",
                        "active": False,
                        "stats": {
                            "atk": 240,
                            "def": 148,
                            "spa": 204,
                            "spd": 148,
                            "spe": 148,
                        },
                        "moves": ["headsmash", "superpower", "flareblitz", "grassknot"],
                        "baseAbility": "reckless",
                        "item": "assaultvest",
                        "pokeball": "pokeball",
                        "ability": "reckless",
                    },
                    {
                        "ident": "p1: Zoroark",
                        "details": "Zoroark, L77, M",
                        "condition": "219/219",
                        "active": False,
                        "stats": {
                            "atk": 166,
                            "def": 137,
                            "spa": 229,
                            "spd": 137,
                            "spe": 206,
                        },
                        "moves": [
                            "sludgebomb",
                            "darkpulse",
                            "flamethrower",
                            "focusblast",
                        ],
                        "baseAbility": "illusion",
                        "item": "choicespecs",
                        "pokeball": "pokeball",
                        "ability": "illusion",
                    },
                    {
                        "ident": "p1: Reuniclus",
                        "details": "Reuniclus, L78, M",
                        "condition": "300/300",
                        "active": False,
                        "stats": {
                            "atk": 106,
                            "def": 162,
                            "spa": 240,
                            "spd": 178,
                            "spe": 92,
                        },
                        "moves": ["calmmind", "shadowball", "psyshock", "recover"],
                        "baseAbility": "magicguard",
                        "item": "lifeorb",
                        "pokeball": "pokeball",
                        "ability": "magicguard",
                    },
                    {
                        "ident": "p1: Moltres",
                        "details": "Moltres, L77",
                        "condition": "265/265",
                        "active": False,
                        "stats": {
                            "atk": 159,
                            "def": 183,
                            "spa": 237,
                            "spd": 175,
                            "spe": 183,
                        },
                        "moves": ["fireblast", "toxic", "hurricane", "roost"],
                        "baseAbility": "flamebody",
                        "item": "leftovers",
                        "pokeball": "pokeball",
                        "ability": "flamebody",
                    },
                ],
            },
            "rqid": 2,
        }

    def test_request_sets_force_switch_to_false(self):
        split_request_message = ["", "request", json.dumps(self.request_json)]
        request(self.battle, split_request_message)
        self.assertEqual((False, False), self.battle.force_switch)

    def test_force_switch_properly_sets_the_force_switch_flag(self):
        self.request_json.pop("active")
        self.request_json[constants.FORCE_SWITCH] = [True, True]
        split_request_message = ["", "request", json.dumps(self.request_json)]
        request(self.battle, split_request_message)
        self.assertEqual((True, True), self.battle.force_switch)

    def test_wait_properly_sets_wait_flag(self):
        self.request_json.pop("active")
        self.request_json[constants.WAIT] = [True, True]
        split_request_message = ["", "request", json.dumps(self.request_json)]
        request(self.battle, split_request_message)
        self.assertEqual(True, self.battle.wait)

    def test_wait_does_not_initialize_pokemon(self):
        self.request_json.pop("active")
        self.request_json[constants.WAIT] = [True, True]
        split_request_message = ["", "request", json.dumps(self.request_json)]
        request(self.battle, split_request_message)
        self.assertEqual(0, len(self.battle.user.reserve))


class TestSwitchOrDrag(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"
        self.battle.user.slot_a.active = Pokemon("pikachu", 100)

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active
        self.battle.opponent.reserve = []

    def test_does_not_add_sandstream_to_impossible_abilities_if_sand_active(self):
        split_msg = ["", "switch", "p2a: caterpie", "Caterpie, L100, M", "100/100"]
        self.battle.weather = constants.SAND
        switch_or_drag(self.battle, split_msg)

        self.assertEqual("caterpie", self.battle.opponent.slot_a.active.name)
        self.assertNotIn(
            "sandstream", self.battle.opponent.slot_a.active.impossible_abilities
        )

    def test_does_not_add_sandstream_to_impossible_abilities_if_heavy_rain_is_active(
        self,
    ):
        split_msg = ["", "switch", "p2a: caterpie", "Caterpie, L100, M", "100/100"]
        self.battle.weather = constants.HEAVY_RAIN
        switch_or_drag(self.battle, split_msg)

        self.assertEqual("caterpie", self.battle.opponent.slot_a.active.name)
        self.assertNotIn(
            "sandstream", self.battle.opponent.slot_a.active.impossible_abilities
        )

    def test_does_not_add_pressure_to_impossible_abilities_gen3(self):
        self.battle.generation = "gen3"
        split_msg = ["", "switch", "p2a: caterpie", "Caterpie, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual("caterpie", self.battle.opponent.slot_a.active.name)
        self.assertNotIn(
            "pressure", self.battle.opponent.slot_a.active.impossible_abilities
        )

    def test_does_not_add_impossible_ability_if_other_side_has_neutralizinggas(self):
        self.battle.user.slot_a.active.ability = "neutralizinggas"
        split_msg = ["", "switch", "p2a: caterpie", "Caterpie, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual("caterpie", self.battle.opponent.slot_a.active.name)
        self.assertNotIn(
            "intimidate", self.battle.opponent.slot_a.active.impossible_abilities
        )

    def test_cramorantgulping_reverts_to_cramorant_in_switchout(self):
        self.battle.opponent.slot_a.active.name = "cramorantgulping"
        split_msg = ["", "switch", "p2a: caterpie", "Caterpie, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual("caterpie", self.battle.opponent.slot_a.active.name)
        self.assertIn("cramorant", [p.name for p in self.battle.opponent.reserve])
        self.assertNotIn(
            "cramorantgulping", [p.name for p in self.battle.opponent.reserve]
        )

    def test_user_switching_in_zaciancrowned_properly_re_initializes_stats(self):
        self.battle.request_json = {
            "active": [],
            "side": {
                "pokemon": [
                    {
                        "ident": "p1: Zacian",
                        "details": "Zacian-Crowned",
                        "condition": "211/325",
                        "active": True,
                        "stats": {
                            "atk": 399,
                            "def": 267,
                            "spa": 176,
                            "spd": 266,
                            "spe": 434,
                        },
                        "moves": [
                            "behemothblade",
                            "swordsdance",
                            "wildcharge",
                            "closecombat",
                        ],
                        "baseAbility": "intrepidsword",
                        "item": "rustedsword",
                        "pokeball": "pokeball",
                        "ability": "intrepidsword",
                        "commanding": False,
                        "reviving": False,
                        "teraType": "Flying",
                        "terastallized": "",
                    }
                ]
            },
        }
        self.battle.user.slot_a.active = Pokemon("weedle", 100)
        zacian_crowned_reserve = Pokemon("zaciancrowned", 100)
        zacian_crowned_reserve.stats = {
            constants.ATTACK: 359,  # should be replaced with 399
            constants.DEFENSE: 267,
            constants.SPECIAL_ATTACK: 176,
            constants.SPECIAL_DEFENSE: 266,
            constants.SPEED: 434,
        }
        self.battle.user.reserve = [zacian_crowned_reserve]
        split_msg = ["", "switch", "p1a: Zacian", "Zacian-Crowned", "211/325"]
        switch_or_drag(self.battle, split_msg)
        self.assertEqual(399, self.battle.user.slot_a.active.stats[constants.ATTACK])

    def test_being_dragged_into_not_zoroark_properly_sets_not_zoroark(self):
        self.battle.request_json = {
            "active": [],
            "side": {
                "pokemon": [
                    {
                        "ident": "p1: Zoroark",
                        "details": "Zoroark, L100, M",
                        "active": False,
                    },
                    {
                        "ident": "p1: Weedle",
                        "details": "Weedle, L100, M",
                        "active": True,
                    },
                ]
            },
        }
        self.battle.reserve = [
            Pokemon("zoroark", 100),
            Pokemon("weedle", 100),
        ]
        split_msg = ["", "drag", "p1a: Weedle", "Weedle, L100, M", "100/100"]
        drag(self.battle, split_msg)

        self.assertEqual("weedle", self.battle.user.slot_a.active.name)

    def test_switch_properly_resets_types_when_pkmn_was_typechanged(self):
        self.battle.opponent.slot_a.active.volatile_statuses.append(
            constants.TYPECHANGE
        )
        self.battle.opponent.slot_a.active.types = ["fire"]
        active = self.battle.opponent.slot_a.active
        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(["bug"], active.types)

    def test_switch_properly_resets_ability_when_pkmn_had_ability_changed(self):
        self.battle.opponent.slot_a.active.ability = "lingeringarmoa"
        self.battle.opponent.slot_a.active.original_ability = "intimidate"
        active = self.battle.opponent.slot_a.active
        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual("intimidate", active.ability)

    def test_increments_rest_turns_by_consequtive_sleeptalks(self):
        self.battle.generation = "gen3"
        active = self.battle.opponent.slot_a.active
        active.gen_3_consecutive_sleep_talks = 1
        active.rest_turns = 1
        active.status = constants.SLEEP
        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(0, active.gen_3_consecutive_sleep_talks)
        self.assertEqual(2, active.rest_turns)

    def test_decrements_sleep_turns_by_consequtive_sleeptalks(self):
        self.battle.generation = "gen3"
        active = self.battle.opponent.slot_a.active
        active.gen_3_consecutive_sleep_talks = 1
        active.sleep_turns = 1
        active.status = constants.SLEEP
        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(0, active.gen_3_consecutive_sleep_talks)
        self.assertEqual(0, active.rest_turns)

    def test_switch_properly_resets_rest_turns_to_2_in_gen5(self):
        self.battle.generation = "gen5"
        active = self.battle.opponent.slot_a.active
        active.rest_turns = 1
        active.status = constants.SLEEP
        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(3, active.rest_turns)

    def test_switch_properly_resets_sleep_turns_to_0_in_gen5(self):
        self.battle.opponent.slot_a.active.volatile_statuses.append(
            constants.TYPECHANGE
        )
        self.battle.generation = "gen5"
        active = self.battle.opponent.slot_a.active
        active.sleep_turns = 1
        active.status = constants.SLEEP
        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(0, active.sleep_turns)

    def test_switch_does_not_reset_sleep_turns_to_0_in_gen4(self):
        self.battle.opponent.slot_a.active.volatile_statuses.append(
            constants.TYPECHANGE
        )
        self.battle.generation = "gen4"
        active = self.battle.opponent.slot_a.active
        active.sleep_turns = 1
        active.status = constants.SLEEP
        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(1, active.sleep_turns)

    def test_switch_opponents_pokemon_successfully_creates_new_pokemon_for_active(self):
        new_pkmn = Pokemon("weedle", 100)
        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(new_pkmn, self.battle.opponent.slot_a.active)

    def test_bot_switching_properly_heals_pokemon_if_it_had_regenerator(self):
        current_active = self.battle.user.slot_a.active
        self.battle.user.slot_a.active.ability = "regenerator"
        self.battle.user.slot_a.active.hp = 1
        self.battle.user.slot_a.active.max_hp = 300
        split_msg = ["", "switch", "p1a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(101, current_active.hp)  # 100 hp from regenerator heal

    def test_bot_switching_with_regenerator_does_not_overheal(self):
        current_active = self.battle.user.slot_a.active
        self.battle.user.slot_a.active.ability = "regenerator"
        self.battle.user.slot_a.active.hp = 250
        self.battle.user.slot_a.active.max_hp = 300
        split_msg = ["", "switch", "p1a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(300, current_active.hp)  # 50 hp from regenerator heal

    def test_fainted_pokemon_switching_does_not_heal(self):
        current_active = self.battle.user.slot_a.active
        self.battle.user.slot_a.active.ability = "regenerator"
        self.battle.user.slot_a.active.hp = 0
        self.battle.user.slot_a.active.fainted = True
        self.battle.user.slot_a.active.max_hp = 300
        split_msg = ["", "switch", "p1a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(
            0, current_active.hp
        )  # no regenerator heal when you are fainted

    def test_nickname_attribute_is_set_when_switching(self):
        # |switch|p2a: Sus|Amoonguss, F|100/100
        split_msg = ["", "switch", "p2a: Sus", "Amoonguss, F", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(self.battle.opponent.slot_a.active.name, "amoonguss")
        self.assertEqual(self.battle.opponent.slot_a.active.nickname, "Sus")

    def test_switch_resets_toxic_count_for_opponent(self):
        self.battle.opponent.side_conditions[constants.TOXIC_COUNT] = 1
        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(0, self.battle.opponent.side_conditions[constants.TOXIC_COUNT])

    def test_switch_resets_toxic_count_for_opponent_when_there_is_no_toxic_count(self):
        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(0, self.battle.opponent.side_conditions[constants.TOXIC_COUNT])

    def test_switch_resets_toxic_count_for_user(self):
        self.battle.user.side_conditions[constants.TOXIC_COUNT] = 1
        split_msg = ["", "switch", "p1a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(0, self.battle.user.side_conditions[constants.TOXIC_COUNT])

    def test_switch_opponents_pokemon_successfully_places_previous_active_pokemon_in_reserve(
        self,
    ):
        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertIn(self.opponent_active, self.battle.opponent.reserve)

    def test_switch_opponents_pokemon_creates_reserve_of_length_1_when_reserve_was_previously_empty(
        self,
    ):
        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(1, len(self.battle.opponent.reserve))

    def test_switch_into_already_seen_pokemon_does_not_create_a_new_pokemon(self):
        already_seen_pokemon = Pokemon("weedle", 100)
        self.battle.opponent.reserve.append(already_seen_pokemon)
        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(1, len(self.battle.opponent.reserve))

    def test_user_switching_causes_pokemon_to_switch(self):
        already_seen_pokemon = Pokemon("weedle", 100)
        self.battle.user.reserve.append(already_seen_pokemon)
        split_msg = ["", "switch", "p1a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(Pokemon("weedle", 100), self.battle.user.slot_a.active)

    def test_user_switching_causes_active_pokemon_to_be_placed_in_reserve(self):
        already_seen_pokemon = Pokemon("weedle", 100)
        self.battle.user.reserve.append(already_seen_pokemon)
        split_msg = ["", "switch", "p1a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(Pokemon("pikachu", 100), self.battle.user.reserve[0])

    def test_user_switching_removes_volatile_statuses(self):
        user_active = self.battle.user.slot_a.active
        already_seen_pokemon = Pokemon("weedle", 100)
        self.battle.user.reserve.append(already_seen_pokemon)
        user_active.volatile_statuses = ["flashfire", "encore", "taunt"]
        user_active.volatile_status_durations["encore"] = 1
        user_active.volatile_status_durations["taunt"] = 2
        split_msg = ["", "switch", "p1a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual([], user_active.volatile_statuses)
        self.assertEqual(0, user_active.volatile_status_durations["encore"])
        self.assertEqual(0, user_active.volatile_status_durations["taunt"])

    def test_already_seen_pokemon_is_the_same_object_as_the_one_in_the_reserve(self):
        already_seen_pokemon = Pokemon("weedle", 100)
        self.battle.opponent.reserve.append(already_seen_pokemon)
        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertIs(already_seen_pokemon, self.battle.opponent.slot_a.active)

    def test_silvally_steel_replaces_silvally(self):
        already_seen_pokemon = Pokemon("silvally", 100)
        self.battle.opponent.reserve.append(already_seen_pokemon)
        split_msg = [
            "",
            "switch",
            "p2a: silvally",
            "Silvally-Steel, L100, M",
            "100/100",
        ]
        switch_or_drag(self.battle, split_msg)

        expected_pokemon = Pokemon("silvallysteel", 100)

        self.assertEqual(expected_pokemon, self.battle.opponent.slot_a.active)

    def test_silvally_steel_with_nickname_replaces_silvally(self):
        already_seen_pokemon = Pokemon("silvally", 100)
        self.battle.opponent.reserve.append(already_seen_pokemon)
        split_msg = [
            "",
            "switch",
            "p2a: notsilvally",
            "Silvally-Steel, L100, M",
            "100/100",
        ]
        switch_or_drag(self.battle, split_msg)

        expected_pokemon = Pokemon("silvallysteel", 100)

        self.assertEqual(expected_pokemon, self.battle.opponent.slot_a.active)

    def test_silvally_replaces_reserve_silvally_with_different_name(self):
        already_seen_pokemon = Pokemon("silvally", 100)
        already_seen_pokemon.unknown_forme = True
        self.battle.opponent.reserve.append(already_seen_pokemon)
        split_msg = [
            "",
            "switch",
            "p2a: notsilvally",
            "Silvally-Steel, L100, M",
            "100/100",
        ]
        switch_or_drag(self.battle, split_msg)

        expected_pokemon = Pokemon("silvallysteel", 100)

        self.assertEqual(expected_pokemon, self.battle.opponent.slot_a.active)
        self.assertNotIn(already_seen_pokemon, self.battle.opponent.reserve)

    def test_silvally_switching_in_preserves_previous_hp(self):
        already_seen_pokemon = Pokemon("silvallysteel", 100)
        already_seen_pokemon.hp = already_seen_pokemon.max_hp / 2
        self.battle.opponent.reserve.append(already_seen_pokemon)
        split_msg = [
            "",
            "switch",
            "p2a: notsilvally",
            "Silvally-Steel, L100, M",
            "50/100",
        ]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(
            self.battle.opponent.slot_a.active.max_hp / 2,
            self.battle.opponent.slot_a.active.hp,
        )

    def test_arceus_ghost_switching_in(self):
        already_seen_pokemon = Pokemon("arceus", 100)
        self.battle.opponent.reserve.append(already_seen_pokemon)
        split_msg = ["", "switch", "p2a: Arceus", "Arceus-Ghost", "100/100"]
        switch_or_drag(self.battle, split_msg)

        expected_pokemon = Pokemon("arceus-ghost", 100)

        self.assertEqual(expected_pokemon, self.battle.opponent.slot_a.active)

    def test_existing_boosts_on_opponents_active_pokemon_are_cleared_when_switching(
        self,
    ):
        self.opponent_active.boosts[constants.ATTACK] = 1
        self.opponent_active.boosts[constants.SPEED] = 1
        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual({}, self.opponent_active.boosts)

    def test_existing_boosts_on_bots_active_pokemon_are_cleared_when_switching(self):
        pkmn = self.battle.user.slot_a.active
        pkmn.boosts[constants.ATTACK] = 1
        pkmn.boosts[constants.SPEED] = 1
        split_msg = ["", "switch", "p1a: pidgey", "Pidgey, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual({}, pkmn.boosts)

    def test_switching_into_the_same_pokemon_does_not_put_that_pokemon_in_the_reserves(
        self,
    ):
        # this is specifically for Zororak
        split_msg = ["", "switch", "p2a: caterpie", "Caterpie, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        self.assertFalse(self.battle.opponent.reserve)

    def test_switching_sets_last_move_to_none(self):
        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        expected_last_move = LastUsedMove(None, "switch weedle", 0)

        self.assertEqual(expected_last_move, self.battle.opponent.slot_a.last_used_move)

    def test_ditto_switching_sets_ability_to_imposter_via_original_ability(self):
        ditto = Pokemon("ditto", 100)
        ditto.ability = "some_ability"
        ditto.original_ability = "imposter"
        ditto.volatile_statuses.append(constants.TRANSFORM)
        self.battle.opponent.slot_a.active = ditto
        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        if self.battle.opponent.reserve[0] != ditto:
            self.fail("Ditto was not moved to reserves")

        self.assertEqual("imposter", ditto.ability)

    def test_ditto_switching_sets_moves_to_empty_list(self):
        ditto = Pokemon("ditto", 100)
        ditto.moves = [Move("tackle"), Move("stringshot")]
        ditto.volatile_statuses.append(constants.TRANSFORM)
        self.battle.opponent.slot_a.active = ditto

        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        if self.battle.opponent.reserve[0] != ditto:
            self.fail("Ditto was not moved to reserves")

        self.assertEqual([], ditto.moves)

    def test_ditto_switching_sets_moves_to_empty_list_for_user(self):
        ditto = Pokemon("ditto", 100)
        ditto.moves = [Move("tackle"), Move("stringshot")]
        ditto.volatile_statuses.append(constants.TRANSFORM)
        self.battle.user.slot_a.active = ditto

        split_msg = ["", "switch", "p1a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        if self.battle.user.reserve[0] != ditto:
            self.fail("Ditto was not moved to reserves")

        self.assertEqual([], ditto.moves)

    def test_ditto_switching_resets_stats(self):
        ditto = Pokemon("ditto", 100)
        ditto.stats = {
            constants.ATTACK: 1,
            constants.DEFENSE: 2,
            constants.SPECIAL_ATTACK: 3,
            constants.SPECIAL_DEFENSE: 4,
            constants.SPEED: 5,
        }
        ditto.volatile_statuses.append(constants.TRANSFORM)
        self.battle.opponent.slot_a.active = ditto

        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        if self.battle.opponent.reserve[0] != ditto:
            self.fail("Ditto was not moved to reserves")

        expected_stats = calculate_stats(ditto.base_stats, ditto.level)

        self.assertEqual(expected_stats, ditto.stats)

    def test_ditto_switching_resets_boosts(self):
        ditto = Pokemon("ditto", 100)
        ditto.boosts = {
            constants.ATTACK: 1,
            constants.DEFENSE: 2,
            constants.SPECIAL_ATTACK: 3,
            constants.SPECIAL_DEFENSE: 4,
            constants.SPEED: 5,
        }
        ditto.volatile_statuses.append(constants.TRANSFORM)
        self.battle.opponent.slot_a.active = ditto

        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        if self.battle.opponent.reserve[0] != ditto:
            self.fail("Ditto was not moved to reserves")

        self.assertEqual({}, ditto.boosts)

    def test_ditto_switching_resets_types(self):
        ditto = Pokemon("ditto", 100)
        ditto.types = ["fairy", "flying"]
        ditto.volatile_statuses.append(constants.TRANSFORM)
        self.battle.opponent.slot_a.active = ditto

        split_msg = ["", "switch", "p2a: weedle", "Weedle, L100, M", "100/100"]
        switch_or_drag(self.battle, split_msg)

        if self.battle.opponent.reserve[0] != ditto:
            self.fail("Ditto was not moved to reserves")

        self.assertEqual(["normal"], ditto.types)

    def test_shed_tail_switching_in_gets_shed_tailing_flag_set_to_false(self):
        self.battle.user.slot_a.shed_tailing = True

        split_msg = [
            "",
            "switch",
            "p1a: Pikachu",
            "Pikachu, L100, M",
            "100/100",
            "[from] Shed Tail",
        ]
        switch_or_drag(self.battle, split_msg)

        self.assertFalse(self.battle.user.slot_a.shed_tailing)

    def test_shed_tail_switching_in_only_keeps_substitute(self):
        self.battle.user.slot_a.active.volatile_statuses = [
            constants.SUBSTITUTE,
            constants.LEECH_SEED,
        ]
        self.battle.user.slot_a.active.boosts[constants.SPEED] = 1
        self.battle.user.slot_a.active.boosts[constants.ATTACK] = -2

        split_msg = [
            "",
            "switch",
            "p1a: Pikachu",
            "Pikachu, L100, M",
            "100/100",
            "[from] Shed Tail",
        ]
        switch_or_drag(self.battle, split_msg)

        self.assertEqual(0, self.battle.user.slot_a.active.boosts[constants.SPEED])
        self.assertEqual(0, self.battle.user.slot_a.active.boosts[constants.ATTACK])
        self.assertEqual(
            [constants.SUBSTITUTE], self.battle.user.slot_a.active.volatile_statuses
        )


class TestHealOrDamage(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.user_active = Pokemon("caterpie", 100)
        self.opponent_active = Pokemon("caterpie", 100)

        # manually set hp to 200 for testing purposes
        self.opponent_active.max_hp = 200
        self.opponent_active.hp = 200

        self.battle.opponent.slot_a.active = self.opponent_active
        self.battle.user.slot_a.active = self.user_active

    def test_heal_from_healing_wish_clears_side_condition(self):
        # |-heal|p1a: Caterpie|100/100|[from] move: Healing Wish
        self.battle.opponent.side_conditions[constants.HEALING_WISH] = 1
        split_msg = [
            "",
            "-heal",
            "p2a: Caterpie",
            "100/100",
            "[from] move: Healing Wish",
        ]
        heal_or_damage(self.battle, split_msg)
        self.assertEqual(
            0, self.battle.opponent.side_conditions[constants.HEALING_WISH]
        )

    def test_damage_sets_opponents_active_pokemon_to_correct_hp(self):
        split_msg = ["", "-damage", "p2a: Caterpie", "80/100"]
        heal_or_damage(self.battle, split_msg)
        self.assertEqual(160, self.battle.opponent.slot_a.active.hp)

    def test_damage_sets_bots_active_pokemon_to_correct_hp(self):
        split_msg = ["", "-damage", "p1a: Caterpie", "150/250"]
        heal_or_damage(self.battle, split_msg)
        self.assertEqual(150, self.battle.user.slot_a.active.hp)

    def test_damage_sets_bots_active_pokemon_to_correct_maxhp(self):
        split_msg = ["", "-damage", "p1a: Caterpie", "150/250"]
        heal_or_damage(self.battle, split_msg)
        self.assertEqual(250, self.battle.user.slot_a.active.max_hp)

    def test_damage_sets_bots_active_pokemon_to_zero_hp(self):
        split_msg = ["", "-damage", "p1a: Caterpie", "0 fnt"]
        heal_or_damage(self.battle, split_msg)
        self.assertEqual(0, self.battle.user.slot_a.active.hp)

    def test_fainted_message_properly_faints_opponents_pokemon(self):
        split_msg = ["", "-damage", "p2a: Caterpie", "0 fnt"]
        heal_or_damage(self.battle, split_msg)
        self.assertEqual(0, self.battle.opponent.slot_a.active.hp)

    def test_damage_caused_by_an_item_properly_sets_opponents_item(self):
        split_msg = ["", "-damage", "p2a: Caterpie", "100/100", "[from] item: Life Orb"]
        heal_or_damage(self.battle, split_msg)
        self.assertEqual("lifeorb", self.battle.opponent.slot_a.active.item)

    def test_damage_caused_by_toxic_increases_side_condition_toxic_counter_for_opponent(
        self,
    ):
        split_msg = ["", "-damage", "p2a: Caterpie", "94/100 tox", "[from] psn"]
        heal_or_damage(self.battle, split_msg)
        self.assertEqual(1, self.battle.opponent.side_conditions[constants.TOXIC_COUNT])

    def test_damage_caused_by_toxic_increases_side_condition_toxic_counter_for_user(
        self,
    ):
        split_msg = ["", "-damage", "p1a: Caterpie", "94/100 tox", "[from] psn"]
        heal_or_damage(self.battle, split_msg)
        self.assertEqual(1, self.battle.user.side_conditions[constants.TOXIC_COUNT])

    def test_toxic_count_increases_to_2(self):
        self.battle.opponent.side_conditions[constants.TOXIC_COUNT] = 1
        split_msg = ["", "-damage", "p2a: Caterpie", "94/100 tox", "[from] psn"]
        heal_or_damage(self.battle, split_msg)
        self.assertEqual(2, self.battle.opponent.side_conditions[constants.TOXIC_COUNT])

    def test_damage_caused_by_non_toxic_damage_does_not_increase_toxic_count(self):
        split_msg = [
            "",
            "-damage",
            "p2a: Caterpie",
            "50/100 tox",
            "[from] item: Life Orb",
        ]
        heal_or_damage(self.battle, split_msg)
        self.assertEqual(0, self.battle.opponent.side_conditions[constants.TOXIC_COUNT])

    def test_healing_from_ability_does_not_set_bots_ability(self):
        self.battle.user.slot_a.active.ability = None
        split_msg = [
            "",
            "-heal",
            "p2a: Caterpie",
            "50/100",
            "[from] ability: Volt Absorb",
            "[of] p1a: Caterpie",
        ]
        heal_or_damage(self.battle, split_msg)
        self.assertIsNone(self.battle.user.slot_a.active.ability)

    def test_healing_from_revivalblessing_for_opponent_pkmn(self):
        amoongus_reserve = Pokemon("amoonguss", 100)
        amoongus_reserve.nickname = "Sus"
        amoongus_reserve.hp = 0
        amoongus_reserve.fainted = True
        self.battle.opponent.reserve = [amoongus_reserve]

        # |-heal|p1: Amoonguss|50/100|[from] move: Revival Blessing
        split_msg = ["", "-heal", "p2a: Sus", "50/100", "[from] move: Revival Blessing"]
        heal_or_damage(self.battle, split_msg)
        self.assertEqual(amoongus_reserve.hp, int(amoongus_reserve.max_hp / 2))

    def test_healing_from_revivalblessing_for_bot_pkmn(self):
        amoongus_reserve = Pokemon("amoonguss", 100)
        amoongus_reserve.nickname = "Sus"
        amoongus_reserve.hp = 0
        amoongus_reserve.fainted = True
        self.battle.user.reserve = [amoongus_reserve]

        split_msg = [
            "",
            "-heal",
            "p1a: Sus",
            "150/301",
            "[from] move: Revival Blessing",
        ]
        heal_or_damage(self.battle, split_msg)
        self.assertEqual(amoongus_reserve.hp, int(amoongus_reserve.max_hp / 2))


class TestActivate(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.user_active_a = Pokemon("caterpie", 100)
        self.user_active_b = Pokemon("weedle", 100)
        self.opponent_active_a = Pokemon("caterpie", 100)
        self.opponent_active_b = Pokemon("weedle", 100)

        # manually set hp to 200 for testing purposes
        self.opponent_active_a.max_hp = 200
        self.opponent_active_a.hp = 200

        self.battle.opponent.slot_a.active = self.opponent_active_a
        self.battle.opponent.slot_b.active = self.opponent_active_b
        self.battle.user.slot_a.active = self.user_active_a
        self.battle.user.slot_b.active = self.user_active_b

    def test_commander_activating_slot_b(self):
        split_msg = [
            "",
            "-activate",
            "p2b: Tatsugiri",
            "ability: Commander",
            "[of] p2a: Dondozo",
        ]
        activate(self.battle, split_msg)
        self.assertIn(
            "commanding", self.battle.opponent.slot_b.active.volatile_statuses
        )
        self.assertIn("commanded", self.battle.opponent.slot_a.active.volatile_statuses)

    def test_commander_activating_slot_a(self):
        split_msg = [
            "",
            "-activate",
            "p2a: Tatsugiri",
            "ability: Commander",
            "[of] p2b: Dondozo",
        ]
        activate(self.battle, split_msg)
        self.assertIn(
            "commanding", self.battle.opponent.slot_a.active.volatile_statuses
        )
        self.assertIn("commanded", self.battle.opponent.slot_b.active.volatile_statuses)

    def test_activating_partially_trapped_whirlpool(self):
        split_msg = [
            "",
            "-activate",
            "p2a: Caterpie",
            "move: Whirlpool",
            "[of] p1a: Luvdisc",
        ]
        activate(self.battle, split_msg)
        self.assertIn(
            "partiallytrapped", self.battle.opponent.slot_a.active.volatile_statuses
        )

    def test_activating_partially_trapped_magmastorm(self):
        split_msg = [
            "",
            "-activate",
            "p2a: Caterpie",
            "move: Magma Storm",
            "[of] p1a: Luvdisc",
        ]
        activate(self.battle, split_msg)
        self.assertIn(
            "partiallytrapped", self.battle.opponent.slot_a.active.volatile_statuses
        )

    def test_does_not_activate_partiallytrapped_when_not_a_partiallytrapping_move(self):
        # this isn't something that would cause an `-activate`, but just to make sure the logic is correct
        split_msg = [
            "",
            "-activate",
            "p2a: Caterpie",
            "move: Tackle",
            "[of] p1a: Luvdisc",
        ]
        activate(self.battle, split_msg)
        self.assertNotIn(
            "partiallytrapped", self.battle.opponent.slot_a.active.volatile_statuses
        )

    def test_does_not_set_consumed_item(self):
        split_msg = [
            "",
            "-activate",
            "p2a: Caterpie",
            "item: Custap Berry",
            "[consumed]",
        ]
        self.battle.opponent.slot_a.active.item = None
        activate(self.battle, split_msg)
        self.assertIsNone(self.battle.opponent.slot_a.active.item)

    def test_sets_ability_from_activate(self):
        split_msg = ["", "-activate", "p2a: Ferrothorn", "ability: Iron Barbs"]
        activate(self.battle, split_msg)
        self.assertEqual("ironbarbs", self.battle.opponent.slot_a.active.ability)

    def test_sets_substitute_hit_from_activate(self):
        split_msg = ["", "-activate", "p2a: Heatran", "Substitute", "[damage]"]
        activate(self.battle, split_msg)
        self.assertTrue(self.battle.opponent.slot_a.active.substitute_hit)


class TestPrepare(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.user_active = Pokemon("caterpie", 100)
        self.opponent_active = Pokemon("caterpie", 100)

        # manually set hp to 200 for testing purposes
        self.opponent_active.max_hp = 200
        self.opponent_active.hp = 200

        self.battle.opponent.slot_a.active = self.opponent_active
        self.battle.user.slot_a.active = self.user_active

    def test_prepare_sets_volatile_status_on_pokemon(self):
        # |-prepare|p1a: Dragapult|Phantom Force
        split_msg = ["", "-prepare", "p2a: Caterpie", "Phantom Force"]
        prepare(self.battle, split_msg)
        self.assertIn(
            "phantomforce", self.battle.opponent.slot_a.active.volatile_statuses
        )


class TestClearAllBoosts(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.user_active = Pokemon("caterpie", 100)
        self.opponent_active = Pokemon("caterpie", 100)

        # manually set hp to 200 for testing purposes
        self.opponent_active.max_hp = 200
        self.opponent_active.hp = 200

        self.battle.opponent.slot_a.active = self.opponent_active
        self.battle.opponent.slot_b.active = Pokemon("pikachu", 100)
        self.battle.user.slot_a.active = self.user_active
        self.battle.user.slot_b.active = Pokemon("pikachu", 100)

    def test_clears_bots_boosts(self):
        split_msg = ["", "-clearallboost"]
        self.battle.user.slot_a.active.boosts = {
            constants.ATTACK: 1,
            constants.DEFENSE: 1,
        }
        clearallboost(self.battle, split_msg)
        self.assertEqual(0, self.battle.user.slot_a.active.boosts[constants.ATTACK])
        self.assertEqual(0, self.battle.user.slot_a.active.boosts[constants.DEFENSE])

    def test_clears_opponents_boosts(self):
        split_msg = ["", "-clearallboost"]
        self.battle.opponent.slot_a.active.boosts = {
            constants.ATTACK: 1,
            constants.DEFENSE: 1,
        }
        clearallboost(self.battle, split_msg)
        self.assertEqual(0, self.battle.opponent.slot_a.active.boosts[constants.ATTACK])
        self.assertEqual(
            0, self.battle.opponent.slot_a.active.boosts[constants.DEFENSE]
        )

    def test_clears_opponents_and_botsboosts(self):
        split_msg = ["", "-clearallboost"]
        self.battle.user.slot_a.active.boosts = {
            constants.ATTACK: 1,
            constants.DEFENSE: 1,
        }
        self.battle.opponent.slot_a.active.boosts = {
            constants.ATTACK: 1,
            constants.DEFENSE: 1,
        }
        clearallboost(self.battle, split_msg)
        self.assertEqual(0, self.battle.user.slot_a.active.boosts[constants.ATTACK])
        self.assertEqual(0, self.battle.user.slot_a.active.boosts[constants.DEFENSE])
        self.assertEqual(0, self.battle.opponent.slot_a.active.boosts[constants.ATTACK])
        self.assertEqual(
            0, self.battle.opponent.slot_a.active.boosts[constants.DEFENSE]
        )


class TestMove(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active

        self.battle.user.slot_a.active = Pokemon("clefable", 100)

    def test_sets_healing_wish_side_condition_when_healing_wish_is_used(self):
        split_msg = ["", "move", "p2a: Caterpie", "Healing Wish", "p2a: Caterpie"]
        move(self.battle, split_msg)
        self.assertEqual(
            1, self.battle.opponent.side_conditions[constants.HEALING_WISH]
        )

    def test_adds_move_to_opponent(self):
        split_msg = ["", "move", "p2a: Caterpie", "String Shot"]

        move(self.battle, split_msg)
        m = Move("String Shot")

        self.assertIn(m, self.battle.opponent.slot_a.active.moves)

    def test_adds_truant_when_truant_pkmn(self):
        self.battle.opponent.slot_a.active.ability = "truant"
        split_msg = ["", "move", "p2a: Slaking", "Earthquake"]
        move(self.battle, split_msg)
        self.assertIn("truant", self.battle.opponent.slot_a.active.volatile_statuses)

    def test_adds_truant_when_slaking_pkmn(self):
        self.battle.opponent.slot_a.active.name = "slaking"
        split_msg = ["", "move", "p2a: Slaking", "Earthquake"]
        move(self.battle, split_msg)
        self.assertIn("truant", self.battle.opponent.slot_a.active.volatile_statuses)

    def test_does_not_set_move_for_magicbounce(self):
        split_msg = [
            "",
            "move",
            "p2a: Caterpie",
            "String Shot",
            "[from] ability: Magic Bounce",
        ]

        move(self.battle, split_msg)
        m = Move("String Shot")

        self.assertNotIn(m, self.battle.opponent.slot_a.active.moves)
        self.assertEqual("magicbounce", self.battle.opponent.slot_a.active.ability)

    def test_does_not_set_move_for_magicbounce_when_still(self):
        # |move|p2a: Espeon|Leech Seed||[from] ability: Magic Bounce|[still]
        split_msg = [
            "",
            "move",
            "p2a: Caterpie",
            "String Shot",
            "[from]Magic Bounce",
            "[still]",
        ]

        move(self.battle, split_msg)
        m = Move("String Shot")

        self.assertNotIn(m, self.battle.opponent.slot_a.active.moves)

    def test_new_move_has_one_pp_less_than_max(self):
        split_msg = ["", "move", "p2a: Caterpie", "String Shot"]

        move(self.battle, split_msg)
        m = self.battle.opponent.slot_a.active.get_move("String Shot")
        expected_pp = m.max_pp - 1

        self.assertEqual(expected_pp, m.current_pp)

    def test_unknown_move_does_not_try_to_decrement(self):
        split_msg = ["", "move", "p2a: Caterpie", "some-random-unknown-move"]

        move(self.battle, split_msg)

    def test_add_revealed_move_does_not_add_move_twice(self):
        split_msg = ["", "move", "p2a: Caterpie", "String Shot"]

        self.battle.opponent.slot_a.active.moves.append(Move("String Shot"))
        move(self.battle, split_msg)

        self.assertEqual(1, len(self.battle.opponent.slot_a.active.moves))

    def test_does_not_decrement_pp_if_move_is_called_by_sleeptalk(self):
        split_msg = ["", "move", "p2a: Caterpie", "String Shot", "[from]Sleep Talk"]
        m = Move("String Shot")
        m.current_pp = 5
        self.battle.opponent.slot_a.active.moves.append(m)
        move(self.battle, split_msg)

        self.assertEqual(5, m.current_pp)

    def test_sets_move_if_doesnt_exist_from_sleeptalk(self):
        split_msg = ["", "move", "p2a: Caterpie", "String Shot", "[from]Sleep Talk"]
        move(self.battle, split_msg)

        self.assertIn(Move("stringshot"), self.battle.opponent.slot_a.active.moves)
        self.assertEqual(
            self.battle.opponent.slot_a.active.moves[0].current_pp,
            self.battle.opponent.slot_a.active.moves[0].max_pp,
        )

    def test_sets_move_if_doesnt_exist_from_move_sleeptalk(self):
        split_msg = [
            "",
            "move",
            "p2a: Caterpie",
            "String Shot",
            "[from]move: Sleep Talk",
        ]
        move(self.battle, split_msg)

        self.assertIn(Move("stringshot"), self.battle.opponent.slot_a.active.moves)
        self.assertEqual(
            self.battle.opponent.slot_a.active.moves[0].current_pp,
            self.battle.opponent.slot_a.active.moves[0].max_pp,
        )

    def test_does_not_decrement_pp_if_move_is_called_by_move_sleeptalk(self):
        split_msg = [
            "",
            "move",
            "p2a: Caterpie",
            "String Shot",
            "[from]move: Sleep Talk",
        ]
        m = Move("String Shot")
        m.current_pp = 5
        self.battle.opponent.slot_a.active.moves.append(m)
        move(self.battle, split_msg)

        self.assertEqual(5, m.current_pp)

    def test_decrements_seen_move_pp_if_seen_again(self):
        split_msg = ["", "move", "p2a: Caterpie", "String Shot"]
        m = Move("String Shot")
        m.current_pp = 5
        self.battle.opponent.slot_a.active.moves.append(m)
        move(self.battle, split_msg)

        self.assertEqual(4, m.current_pp)

    def test_properly_sets_last_used_move(self):
        split_msg = ["", "move", "p2a: Caterpie", "String Shot"]

        move(self.battle, split_msg)

        expected_last_used_move = LastUsedMove(
            pokemon_name="caterpie", move="stringshot", turn=0
        )

        self.assertEqual(
            expected_last_used_move, self.battle.opponent.slot_a.last_used_move
        )

    def test_using_status_move_makes_assaultvest_impossible(self):
        split_msg = ["", "move", "p2a: Caterpie", "String Shot"]
        self.battle.opponent.last_used_move = LastUsedMove("caterpie", "tackle", 0)

        move(self.battle, split_msg)

        self.assertIn(
            constants.ASSAULT_VEST, self.battle.opponent.slot_a.active.impossible_items
        )

    def test_using_nonstatus_move_does_not_make_assultvest_impossible(self):
        split_msg = ["", "move", "p2a: Caterpie", "Tackle"]
        self.battle.opponent.last_used_move = LastUsedMove("caterpie", "tackle", 0)

        move(self.battle, split_msg)

        self.assertNotIn(
            constants.ASSAULT_VEST, self.battle.opponent.slot_a.active.impossible_items
        )

    def test_removes_volatilestatus_if_pkmn_has_it_when_using_move(self):
        self.battle.opponent.slot_a.active.volatile_statuses = ["phantomforce"]
        split_msg = ["", "move", "p2a: Caterpie", "Phantom Force", "[from] lockedmove"]

        move(self.battle, split_msg)

        self.assertEqual([], self.battle.opponent.slot_a.active.volatile_statuses)

    def test_increments_encore_duration_when_using_move_having_been_encored(self):
        self.battle.opponent.slot_a.active.volatile_statuses = ["encore"]
        self.battle.opponent.slot_a.active.volatile_status_durations["encore"] = 0
        split_msg = ["", "move", "p2a: Caterpie", "Tackle"]
        move(self.battle, split_msg)
        self.assertEqual(
            1, self.battle.opponent.slot_a.active.volatile_status_durations["encore"]
        )

    def test_increments_taunt_duration_when_using_move_having_been_taunted(self):
        self.battle.opponent.slot_a.active.volatile_statuses = [constants.TAUNT]
        self.battle.opponent.slot_a.active.volatile_status_durations[
            constants.TAUNT
        ] = 0
        split_msg = ["", "move", "p2a: Caterpie", "Tackle"]
        move(self.battle, split_msg)
        self.assertEqual(
            1,
            self.battle.opponent.slot_a.active.volatile_status_durations[
                constants.TAUNT
            ],
        )

    def test_removes_destinybond_if_it_exists_in_volatiles_when_using_destinybond(self):
        self.battle.opponent.slot_a.active.volatile_statuses = ["destinybond"]
        split_msg = ["", "move", "p2a: Caterpie", "Destiny Bond"]

        move(self.battle, split_msg)

        self.assertEqual([], self.battle.opponent.slot_a.active.volatile_statuses)

    def test_removes_destinybond_if_it_exists_in_volatiles_when_not_using_destinybond(
        self,
    ):
        self.battle.opponent.slot_a.active.volatile_statuses = ["destinybond"]
        split_msg = ["", "move", "p2a: Caterpie", "Tackle"]

        move(self.battle, split_msg)

        self.assertEqual([], self.battle.opponent.slot_a.active.volatile_statuses)

    def test_sets_can_have_choice_item_to_false_if_two_different_moves_are_used_when_the_pkmn_has_an_unknown_item(
        self,
    ):
        self.battle.opponent.slot_a.active.can_have_choice_item = True
        split_msg = ["", "move", "p2a: Caterpie", "String Shot"]
        self.battle.opponent.last_used_move = LastUsedMove("caterpie", "tackle", 0)

        move(self.battle, split_msg)

        self.assertFalse(self.battle.opponent.slot_a.active.can_have_choice_item)

    def test_using_a_boosting_status_move_sets_can_have_choice_item_to_false(self):
        self.battle.opponent.slot_a.active.can_have_choice_item = True
        split_msg = ["", "move", "p2a: Caterpie", "Dragon Dance"]

        move(self.battle, split_msg)

        self.assertFalse(self.battle.opponent.slot_a.active.can_have_choice_item)

    def test_using_a_boosting_physical_move_does_not_set_can_have_choice_item_to_false(
        self,
    ):
        self.battle.opponent.slot_a.active.can_have_choice_item = True
        split_msg = ["", "move", "p2a: Caterpie", "Scale Shot"]

        move(self.battle, split_msg)

        self.assertTrue(self.battle.opponent.slot_a.active.can_have_choice_item)

    def test_using_a_boosting_special_move_does_not_set_can_have_choice_item_to_false(
        self,
    ):
        self.battle.opponent.slot_a.active.can_have_choice_item = True
        split_msg = ["", "move", "p2a: Caterpie", "Scale Shot"]

        move(self.battle, split_msg)

        self.assertTrue(self.battle.opponent.slot_a.active.can_have_choice_item)

    def test_does_not_set_item_to_unknow_if_choice_item_was_not_inferred_and_two_different_moves_were_used(
        self,
    ):
        self.battle.opponent.slot_a.active.can_have_choice_item = True
        self.battle.opponent.slot_a.active.item = "choiceband"
        self.battle.opponent.slot_a.active.item_inferred = False
        split_msg = ["", "move", "p2a: Caterpie", "String Shot"]
        self.battle.opponent.last_used_move = LastUsedMove("caterpie", "tackle", 0)

        move(self.battle, split_msg)

        self.assertEqual(constants.CHOICE_BAND, self.battle.opponent.slot_a.active.item)

    def test_does_not_set_item_to_unknown_if_the_known_item_is_not_a_choice_item_and_two_different_moves_are_used(
        self,
    ):
        self.battle.opponent.slot_a.active.can_have_choice_item = True
        self.battle.opponent.slot_a.active.item = "leftovers"
        split_msg = ["", "move", "p2a: Caterpie", "String Shot"]
        self.battle.opponent.last_used_move = LastUsedMove("caterpie", "tackle", 0)

        move(self.battle, split_msg)

        self.assertEqual("leftovers", self.battle.opponent.slot_a.active.item)

    def test_does_not_set_can_have_choice_item_to_false_if_the_same_move_is_used_when_the_pkmn_has_an_unknown_item(
        self,
    ):
        self.battle.opponent.slot_a.active.can_have_choice_item = True
        split_msg = ["", "move", "p2a: Caterpie", "Tackle"]
        self.battle.opponent.last_used_move = LastUsedMove("caterpie", "tackle", 0)

        move(self.battle, split_msg)

        self.assertTrue(self.battle.opponent.slot_a.active.can_have_choice_item)

    def test_sets_can_have_choice_item_to_false_even_if_item_is_known(self):
        # if the item is known - this flag doesn't matter anyways
        self.battle.opponent.slot_a.active.can_have_choice_item = True
        self.battle.opponent.slot_a.active.item = "leftovers"
        split_msg = ["", "move", "p2a: Caterpie", "String Shot"]
        self.battle.opponent.last_used_move = LastUsedMove("caterpie", "tackle", 0)

        move(self.battle, split_msg)

        self.assertFalse(self.battle.opponent.slot_a.active.can_have_choice_item)

    def test_sets_life_orb_as_impossible_if_damaging_move_is_used(self):
        # if a damaging move is used, we no longer want to guess lifeorb as an item
        split_msg = ["", "move", "p2a: Caterpie", "Tackle"]

        move(self.battle, split_msg)

        self.assertIn(
            constants.LIFE_ORB, self.battle.opponent.slot_a.active.impossible_items
        )

    def test_does_not_set_can_life_orb_to_impossible_if_pokemon_could_have_sheerforce(
        self,
    ):
        # mawile could have sheerforce
        # we shouldn't set the lifeorb flag to False because sheerforce doesn't reveal lifeorb when a damaging move is used
        self.battle.opponent.slot_a.active.name = "mawile"
        split_msg = ["", "move", "p2a: Mawile", "Tackle"]

        move(self.battle, split_msg)

        self.assertNotIn(
            constants.LIFE_ORB, self.battle.opponent.slot_a.active.impossible_items
        )

    def test_does_not_set_life_orb_to_impossible_if_pokemon_could_have_magic_guard(
        self,
    ):
        # clefable could have magic guard
        # we shouldn't set the lifeorb flag to False because magic guard doesn't reveal lifeorb when a damaging move is used
        self.battle.opponent.slot_a.active.name = "clefable"
        split_msg = ["", "move", "p2a: Clefable", "Tackle"]

        move(self.battle, split_msg)

        self.assertNotIn(
            constants.LIFE_ORB, self.battle.opponent.slot_a.active.impossible_items
        )

    def test_adds_normal_gem_to_impossible_items(self):
        split_msg = ["", "move", "p2a: Clefable", "Tackle"]

        move(self.battle, split_msg)
        self.assertIn("normalgem", self.battle.opponent.slot_a.active.impossible_items)

    def test_adds_flying_gem_to_impossible_items(self):
        split_msg = ["", "move", "p2a: Clefable", "Acrobatics"]

        move(self.battle, split_msg)
        self.assertIn("flyinggem", self.battle.opponent.slot_a.active.impossible_items)

    def test_does_not_add_gem_if_non_damaging_move(self):
        split_msg = ["", "move", "p2a: Clefable", "Protect"]

        move(self.battle, split_msg)
        self.assertNotIn(
            "normalgem", self.battle.opponent.slot_a.active.impossible_items
        )

    def test_wish_sets_battler_wish(self):
        split_msg = ["", "move", "p1a: Clefable", "Wish", "p1a: Clefable"]

        move(self.battle, split_msg)

        expected_wish = (2, self.battle.user.slot_a.active.max_hp / 2)

        self.assertEqual(expected_wish, self.battle.user.slot_a.wish)

    def test_failed_wish_does_not_set_wish(self):
        self.battle.user.wish = (1, 100)
        split_msg = ["", "move", "p1a: Clefable", "Wish", "[still]"]

        move(self.battle, split_msg)

        expected_wish = (1, 100)

        self.assertEqual(expected_wish, self.battle.user.wish)

    def test_removes_volatile_status_duration_for_protect_on_non_protect_move(self):
        self.battle.user.slot_a.active.volatile_status_durations[constants.PROTECT] = 1
        split_msg = ["", "move", "p1a: Clefable", "Wish", "[still]"]

        move(self.battle, split_msg)

        self.assertEqual(
            0,
            self.battle.user.slot_a.active.volatile_status_durations[constants.PROTECT],
        )


class TestTrickRoom(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active

    def test_starts_trickroom_properly(self):
        split_msg = [
            "",
            "-fieldstart",
            "move: Trick Room",
            "p1a: Bronzong",
        ]

        fieldstart(self.battle, split_msg)

        self.assertEqual(True, self.battle.trick_room)
        self.assertEqual(5, self.battle.trick_room_turns_remaining)

    def test_removes_trickroom_properly(self):
        split_msg = [
            "",
            "-fieldend",
            "move: Trick Room",
        ]

        fieldend(self.battle, split_msg)

        self.assertEqual(False, self.battle.trick_room)
        self.assertEqual(0, self.battle.trick_room_turns_remaining)


class TestWeather(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active
        self.user_active = Pokemon("caterpie", 100)
        self.battle.user.slot_a.active = self.user_active

    def test_starts_weather_properly(self):
        split_msg = [
            "",
            "-weather",
            "RainDance",
            "[from] ability: Drizzle",
            "[of] p2a: Caterpie",
        ]

        weather(self.battle, split_msg)

        self.assertEqual("raindance", self.battle.weather)


# |-setboost|p2a: Linoone|atk|6|[from] move: Belly Drum
class TestSetBoost(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.user_active = Pokemon("weedle", 100)
        self.battle.user.slot_a.active = self.user_active

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active

    def test_set_boost_to_6_from_bellydrum(self):
        split_msg = [
            "",
            "-setboost",
            "p2a: Linoone",
            "atk",
            "6",
            "[from] move: Belly Drum",
        ]
        setboost(self.battle, split_msg)

        expected_boosts = {constants.ATTACK: 6}

        self.assertEqual(expected_boosts, self.battle.opponent.slot_a.active.boosts)

    def test_set_boost_to_6_even_when_at_negative_from_bellydrum(self):
        self.battle.opponent.slot_a.active.boosts[constants.ATTACK] = -3
        split_msg = [
            "",
            "-setboost",
            "p2a: Linoone",
            "atk",
            "6",
            "[from] move: Belly Drum",
        ]
        setboost(self.battle, split_msg)

        expected_boosts = {constants.ATTACK: 6}

        self.assertEqual(expected_boosts, self.battle.opponent.slot_a.active.boosts)


class TestBoostAndUnboost(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.user_active = Pokemon("weedle", 100)
        self.battle.user.slot_a.active = self.user_active

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active

    def test_opponent_boost_properly_updates_opponent_pokemons_boosts(self):
        split_msg = ["", "boost", "p2a: Weedle", "atk", "1"]
        boost(self.battle, split_msg)

        expected_boosts = {constants.ATTACK: 1}

        self.assertEqual(expected_boosts, self.battle.opponent.slot_a.active.boosts)

    def test_unboost_works_properly_on_opponent(self):
        split_msg = ["", "boost", "p2a: Weedle", "atk", "1"]
        unboost(self.battle, split_msg)

        expected_boosts = {constants.ATTACK: -1}

        self.assertEqual(expected_boosts, self.battle.opponent.slot_a.active.boosts)

    def test_unboost_does_not_lower_below_negative_6(self):
        self.battle.opponent.slot_a.active.boosts[constants.ATTACK] = -6
        split_msg = ["", "unboost", "p2a: Weedle", "atk", "2"]
        unboost(self.battle, split_msg)

        expected_boosts = {constants.ATTACK: -6}

        self.assertEqual(
            expected_boosts, dict(self.battle.opponent.slot_a.active.boosts)
        )

    def test_unboost_lowers_one_when_it_hits_the_limit(self):
        self.battle.opponent.slot_a.active.boosts[constants.ATTACK] = -5
        split_msg = ["", "unboost", "p2a: Weedle", "atk", "2"]
        unboost(self.battle, split_msg)

        expected_boosts = {constants.ATTACK: -6}

        self.assertEqual(
            expected_boosts, dict(self.battle.opponent.slot_a.active.boosts)
        )

    def test_boost_does_not_lower_below_negative_6(self):
        self.battle.opponent.slot_a.active.boosts[constants.ATTACK] = 6
        split_msg = ["", "boost", "p2a: Weedle", "atk", "2"]
        boost(self.battle, split_msg)

        expected_boosts = {constants.ATTACK: 6}

        self.assertEqual(
            expected_boosts, dict(self.battle.opponent.slot_a.active.boosts)
        )

    def test_boost_lowers_one_when_it_hits_the_limit(self):
        self.battle.opponent.slot_a.active.boosts[constants.ATTACK] = 5
        split_msg = ["", "boost", "p2a: Weedle", "atk", "2"]
        boost(self.battle, split_msg)

        expected_boosts = {constants.ATTACK: 6}

        self.assertEqual(
            expected_boosts, dict(self.battle.opponent.slot_a.active.boosts)
        )

    def test_unboost_works_properly_on_user(self):
        split_msg = ["", "boost", "p1a: Caterpie", "atk", "1"]
        unboost(self.battle, split_msg)

        expected_boosts = {constants.ATTACK: -1}

        self.assertEqual(expected_boosts, self.battle.user.slot_a.active.boosts)

    def test_user_boosts_updates_properly(self):
        split_msg = ["", "boost", "p1a: Caterpie", "atk", "1"]
        boost(self.battle, split_msg)

        expected_boosts = {constants.ATTACK: 1}

        self.assertEqual(expected_boosts, self.battle.user.slot_a.active.boosts)

    def test_multiple_boost_properly_updates(self):
        split_msg = ["", "boost", "p2a: Weedle", "atk", "1"]
        boost(self.battle, split_msg)
        boost(self.battle, split_msg)

        expected_boosts = {constants.ATTACK: 2}

        self.assertEqual(expected_boosts, self.battle.opponent.slot_a.active.boosts)


class TestStatus(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.battle.opponent.slot_a.active = Pokemon("caterpie", 100)
        self.battle.user.slot_a.active = Pokemon("caterpie", 100)

    def test_opponents_active_pokemon_has_status_properly_set(self):
        split_msg = ["", "-status", "p2a: Caterpie", "brn"]
        status(self.battle, split_msg)

        self.assertEqual(self.battle.opponent.slot_a.active.status, constants.BURN)

    def test_rest_turns_set_to_3_on_rest(self):
        split_msg = ["", "-status", "p2a: Caterpie", "slp", "[from] move: Rest"]
        status(self.battle, split_msg)

        self.assertEqual(self.battle.opponent.slot_a.active.status, constants.SLEEP)
        self.assertEqual(self.battle.opponent.slot_a.active.rest_turns, 3)

    def test_rest_turns_at_0_and_sleep_turns_at_0_from_nonrest_sleep(self):
        split_msg = ["", "-status", "p2a: Caterpie", "slp", "[from] move: Sleep powder"]
        status(self.battle, split_msg)

        self.assertEqual(self.battle.opponent.slot_a.active.status, constants.SLEEP)
        self.assertEqual(self.battle.opponent.slot_a.active.rest_turns, 0)
        self.assertEqual(self.battle.opponent.slot_a.active.sleep_turns, 0)

    def test_bots_active_pokemon_has_status_properly_set(self):
        split_msg = ["", "-status", "p1a: Caterpie", "brn"]
        status(self.battle, split_msg)

        self.assertEqual(self.battle.user.slot_a.active.status, constants.BURN)


class TestCureStatus(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active
        self.battle.opponent.slot_b.active = Pokemon("charmander", 100)

        self.opponent_reserve = Pokemon("pikachu", 100)
        self.battle.opponent.reserve = [self.opponent_active, self.opponent_reserve]

        self.battle.user.slot_a.active = Pokemon("weedle", 100)

    def test_curestatus_resets_toxic_count(self):
        self.battle.opponent.slot_a.active.status = constants.TOXIC
        self.battle.opponent.side_conditions[constants.TOXIC_COUNT] = 3
        split_msg = ["", "-curestatus", "p2: Caterpie", "tox", "[msg]"]
        curestatus(self.battle, split_msg)

        self.assertEqual(None, self.battle.opponent.slot_a.active.status)
        self.assertEqual(0, self.battle.opponent.side_conditions[constants.TOXIC_COUNT])

    def test_curestatus_works_on_active_pokemon(self):
        self.opponent_active.status = constants.BURN
        split_msg = ["", "-curestatus", "p2: Caterpie", "brn", "[msg]"]
        curestatus(self.battle, split_msg)

        self.assertEqual(None, self.opponent_active.status)

    def test_curestatus_works_on_active_pokemon_for_bot(self):
        self.battle.user.slot_a.active.status = constants.BURN
        split_msg = ["", "-curestatus", "p1: Weedle", "brn", "[msg]"]
        curestatus(self.battle, split_msg)

        self.assertEqual(None, self.battle.user.slot_a.active.status)

    def test_curestatus_works_on_reserve_pokemon(self):
        self.opponent_reserve.status = constants.BURN
        split_msg = ["", "-curestatus", "p2: Pikachu", "brn", "[msg]"]
        curestatus(self.battle, split_msg)

        self.assertEqual(None, self.opponent_reserve.status)

    def test_curestatus_sets_sleep_and_rest_turns_to_0(self):
        self.opponent_reserve.status = constants.SLEEP
        self.opponent_reserve.sleep_turns = 1
        self.opponent_reserve.rest_turns = 1
        split_msg = ["", "-curestatus", "p2: Pikachu", "slp", "[msg]"]
        curestatus(self.battle, split_msg)

        self.assertEqual(0, self.opponent_reserve.sleep_turns)
        self.assertEqual(0, self.opponent_reserve.rest_turns)


class TestGetDamageDealt(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active
        self.battle.opponent.slot_b.active = Pokemon("torkoal", 100)

        self.user_active = Pokemon("weedle", 100)
        self.battle.user.slot_a.active = self.user_active
        self.battle.user.slot_b.active = Pokemon("charmander", 100)

    def test_gets_damage_dealt_basic_case(self):
        self.battle.opponent.slot_a.active.hp = 100
        self.battle.opponent.slot_a.active.max_hp = 100
        full_message = [
            "|move|p1b: Charmander|Tackle|p2a: Caterpie",
            "|-damage|p2a: Caterpie|75/100",
        ]
        split_msg = full_message[0].split("|")
        next_messages = full_message[1:]

        damage_dealt = get_damage_dealt(self.battle, split_msg, next_messages)
        self.assertEqual(1, len(damage_dealt))
        self.assertEqual(0.25, damage_dealt[0].percent_damage)
        self.assertEqual("tackle", damage_dealt[0].move)

    def test_does_not_get_damage_dealt_for_teammate(self):
        full_message = [
            "|move|p1b: Calyrex|Astral Barrage|p2a: Lunala|[spread] p1a,p2b",
            "|-supereffective|p2a: Lunala",
            "|-damage|p1a: Lunala|0 fnt",
            "|-damage|p2b: Torkoal|0 fnt",
            "|faint|p1a: Lunala",
            "|faint|p2b: Torkoal",
        ]
        split_msg = full_message[0].split("|")
        next_messages = full_message[1:]

        damage_dealt = get_damage_dealt(self.battle, split_msg, next_messages)
        self.assertEqual(1, len(damage_dealt))

    def test_gets_damage_dealt_crit(self):
        self.battle.opponent.slot_a.active.hp = 100
        self.battle.opponent.slot_a.active.max_hp = 100
        full_message = [
            "|move|p1b: Charmander|Tackle|p2a: Caterpie",
            "|-crit|p2a: Caterpie",
            "|-damage|p2a: Caterpie|75/100",
        ]
        split_msg = full_message[0].split("|")
        next_messages = full_message[1:]

        damage_dealt = get_damage_dealt(self.battle, split_msg, next_messages)
        self.assertEqual(1, len(damage_dealt))
        self.assertEqual(True, damage_dealt[0].crit)

    def test_no_damage_dealt(self):
        self.battle.opponent.slot_a.active.hp = 100
        self.battle.opponent.slot_a.active.max_hp = 100
        full_message = [
            "|move|p1b: Charmander|Tackle|p2a: Caterpie",
            "|-activate|p2a: Caterpie|move: Protect",
            "|",
            "|upkeep",
        ]
        split_msg = full_message[0].split("|")
        next_messages = full_message[1:]

        damage_dealt = get_damage_dealt(self.battle, split_msg, next_messages)
        self.assertEqual(0, len(damage_dealt))

    def test_sets_spread(self):
        # |move|p1b: Calyrex|Astral Barrage|p2a: Lunala|[spread] p2a,p2b
        # |-supereffective|p2a: Lunala
        # |-damage|p2a: Lunala|0 fnt
        # |-damage|p2b: Torkoal|0 fnt
        # |faint|p2a: Lunala
        # |faint|p2b: Torkoal
        full_message = [
            "|move|p1b: Calyrex|Astral Barrage|p2a: Lunala|[spread] p2a,p2b",
            "|-supereffective|p2a: Lunala",
            "|-damage|p2a: Lunala|0 fnt",
            "|-damage|p2b: Torkoal|0 fnt",
            "|faint|p2a: Lunala",
            "|faint|p2b: Torkoal",
        ]
        split_msg = full_message[0].split("|")
        next_messages = full_message[1:]

        damage_dealt = get_damage_dealt(self.battle, split_msg, next_messages)
        self.assertEqual(2, len(damage_dealt))
        self.assertEqual(True, damage_dealt[0].spread)
        self.assertEqual(True, damage_dealt[1].spread)

    def test_only_one_damage_dealt_when_spread_with_one_protect(self):
        full_message = [
            "|move|p1b: Calyrex|Astral Barrage|p2a: Lunala|[spread] p2a,p2b",
            "|-activate|p2a: Lunala|move: Protect",
            "|-damage|p2b: Torkoal|0 fnt",
            "|faint|p2b: Torkoal" "|",
            "|upkeep",
        ]
        split_msg = full_message[0].split("|")
        next_messages = full_message[1:]

        damage_dealt = get_damage_dealt(self.battle, split_msg, next_messages)
        self.assertEqual(1, len(damage_dealt))
        self.assertEqual(True, damage_dealt[0].spread)

    def test_only_one_damage_dealt_when_spread_with_one_miss(self):
        full_message = [
            "|move|p1b: Calyrex|Muddy Water|p2a: Lunala|[spread] p2a,p2b",
            "|-miss|p2a: Calyrex|p2a: Lunala",
            "|-damage|p2b: Torkoal|0 fnt",
            "|faint|p2b: Torkoal" "|",
            "|upkeep",
        ]
        split_msg = full_message[0].split("|")
        next_messages = full_message[1:]

        damage_dealt = get_damage_dealt(self.battle, split_msg, next_messages)
        self.assertEqual(1, len(damage_dealt))
        self.assertEqual(True, damage_dealt[0].spread)

    def test_does_not_set_spread(self):
        full_message = [
            "|move|p1b: Calyrex|Astral Barrage|p2a: Lunala",
            "|-supereffective|p2a: Lunala",
            "|-damage|p2a: Lunala|0 fnt",
            "|faint|p2a: Lunala",
        ]
        split_msg = full_message[0].split("|")
        next_messages = full_message[1:]

        damage_dealt = get_damage_dealt(self.battle, split_msg, next_messages)
        self.assertEqual(1, len(damage_dealt))
        self.assertEqual(False, damage_dealt[0].spread)


class TestStartVolatileStatus(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active

        self.user_active = Pokemon("weedle", 100)
        self.battle.user.slot_a.active = self.user_active

    def test_sets_slowstart_duration_when_slowstart_activates(self):
        split_msg = ["", "-start", "p2a: Caterpie", "Slow Start"]
        start_volatile_status(self.battle, split_msg)

        self.assertEqual(
            6,
            self.battle.opponent.slot_a.active.volatile_status_durations[
                constants.SLOW_START
            ],
        )

    def test_volatile_status_is_set_on_opponent_pokemon(self):
        split_msg = ["", "-start", "p2a: Caterpie", "Encore"]
        start_volatile_status(self.battle, split_msg)

        expected_volatile_statuese = ["encore"]

        self.assertEqual(
            expected_volatile_statuese,
            self.battle.opponent.slot_a.active.volatile_statuses,
        )

    def test_substitute_gets_substitute_hit_flag_set_to_false(self):
        self.battle.user.slot_a.active.max_hp = 100
        self.battle.user.slot_a.active.hp = 100

        self.battle.opponent.slot_a.active.hp = 100
        self.battle.user.slot_a.active.hp = 100

        messages = [
            "|move|p2a: Pikachu|Substitute|p2a: Pikachu",
            "|-start|p2a: Pikachu|Substitute",
            "|-damage|p2a: Pikachu|75/100",  # damage from sub should not be caught
        ]

        split_msg = messages[1].split("|")

        start_volatile_status(self.battle, split_msg)
        self.assertFalse(self.battle.opponent.slot_a.active.substitute_hit)

    def test_substitute_gets_shed_tailing_flag_set_to_true(self):
        self.battle.user.slot_a.active.max_hp = 100
        self.battle.user.slot_a.active.hp = 100

        self.battle.opponent.slot_a.active.hp = 100
        self.battle.user.slot_a.active.hp = 100

        messages = [
            "|move|p1a: Cyclizar|Shed Tail|p1a: Cyclizar",
            "|-start|p1a: Cyclizar|Substitute|[from] move: Shed Tail",
            "|-damage|p1a: Cyclizar|50/100",  # damage from sub should not be caught
        ]

        split_msg = messages[1].split("|")

        start_volatile_status(self.battle, split_msg)
        self.assertTrue(self.battle.user.slot_a.shed_tailing)

    def test_flashfire_sets_ability_on_opponent(self):
        split_msg = ["", "-start", "p2a: Caterpie", "ability: Flash Fire"]
        start_volatile_status(self.battle, split_msg)

        self.assertEqual("flashfire", self.battle.opponent.slot_a.active.ability)

    def test_flashfire_sets_ability_on_bot(self):
        split_msg = ["", "-start", "p1a: Caterpie", "ability: Flash Fire"]
        start_volatile_status(self.battle, split_msg)

        self.assertEqual("flashfire", self.battle.user.slot_a.active.ability)

    def test_volatile_status_is_set_on_user_pokemon(self):
        split_msg = ["", "-start", "p1a: Weedle", "Encore"]
        start_volatile_status(self.battle, split_msg)

        expected_volatile_statuese = ["encore"]

        self.assertEqual(
            expected_volatile_statuese, self.battle.user.slot_a.active.volatile_statuses
        )

    def test_adds_volatile_status_from_move_string(self):
        split_msg = ["", "-start", "p1a: Weedle", "move: Taunt"]
        start_volatile_status(self.battle, split_msg)

        expected_volatile_statuese = ["taunt"]

        self.assertEqual(
            expected_volatile_statuese, self.battle.user.slot_a.active.volatile_statuses
        )

    def test_does_not_add_the_same_volatile_status_twice(self):
        self.battle.opponent.slot_a.active.volatile_statuses = ["encore"]
        split_msg = ["", "-start", "p2a: Caterpie", "Encore"]
        start_volatile_status(self.battle, split_msg)

        expected_volatile_statuese = ["encore"]

        self.assertEqual(
            expected_volatile_statuese,
            self.battle.opponent.slot_a.active.volatile_statuses,
        )

    def test_doubles_hp_when_dynamax_starts_for_opponent(self):
        split_msg = ["", "-start", "p2a: Caterpie", "Dynamax"]
        hp, maxhp = (
            self.battle.opponent.slot_a.active.hp,
            self.battle.opponent.slot_a.active.max_hp,
        )
        start_volatile_status(self.battle, split_msg)

        self.assertEqual(hp * 2, self.battle.opponent.slot_a.active.hp)
        self.assertEqual(maxhp * 2, self.battle.opponent.slot_a.active.max_hp)

    def test_doubles_hp_when_dynamax_starts_for_bot(self):
        split_msg = ["", "-start", "p1a: Caterpie", "Dynamax"]
        hp, maxhp = (
            self.battle.user.slot_a.active.hp,
            self.battle.user.slot_a.active.max_hp,
        )
        start_volatile_status(self.battle, split_msg)

        self.assertEqual(hp * 2, self.battle.user.slot_a.active.hp)
        self.assertEqual(maxhp * 2, self.battle.user.slot_a.active.max_hp)

    def test_terastallize(self):
        split_msg = ["", "-terastallize", "p2a: Caterpie", "Fire"]
        terastallize(self.battle, split_msg)

        self.assertTrue(self.battle.opponent.slot_a.active.terastallized)

    def test_terastallize_sets_tera_type(self):
        split_msg = ["", "-terastallize", "p2a: Caterpie", "Fire"]
        terastallize(self.battle, split_msg)

        self.assertEqual("fire", self.battle.opponent.slot_a.active.tera_type)

    def test_sets_ability(self):
        # |-start|p1a: Cinderace|typechange|Fighting|[from] ability: Libero
        split_msg = [
            "",
            "-start",
            "p2a: Cinderace",
            "typechange",
            "Fighting",
            "[from] ability: Libero",
        ]
        start_volatile_status(self.battle, split_msg)

        self.assertEqual("libero", self.battle.opponent.slot_a.active.ability)

    def test_typechange_starts_volatilestatus(self):
        # |-start|p1a: Cinderace|typechange|Fighting|[from] ability: Libero
        split_msg = [
            "",
            "-start",
            "p2a: Cinderace",
            "typechange",
            "Fighting",
            "[from] ability: Libero",
        ]
        start_volatile_status(self.battle, split_msg)

        self.assertIn(
            constants.TYPECHANGE, self.battle.opponent.slot_a.active.volatile_statuses
        )

    def test_getting_confused_makes_lumberry_impossible(self):
        split_msg = [
            "",
            "-start",
            "p2a: Cinderace",
            "Confusion",
        ]
        start_volatile_status(self.battle, split_msg)

        self.assertIn("lumberry", self.battle.opponent.slot_a.active.impossible_items)

    def test_getting_confused_from_fatigue_removes_lockedmove(self):
        self.battle.opponent.slot_a.active.volatile_statuses.append("lockedmove")
        self.battle.opponent.slot_a.active.volatile_status_durations[
            constants.LOCKED_MOVE
        ] = 1
        split_msg = ["", "-start", "p2a: Cinderace", "Confusion", "[fatigue]"]
        start_volatile_status(self.battle, split_msg)

        self.assertNotIn(
            constants.LOCKED_MOVE, self.battle.opponent.slot_a.active.volatile_statuses
        )
        self.assertEqual(
            0,
            self.battle.opponent.slot_a.active.volatile_status_durations[
                constants.LOCKED_MOVE
            ],
        )

    def test_typechange_changes_the_type_of_the_user(self):
        # |-start|p1a: Cinderace|typechange|Fighting|[from] ability: Libero
        split_msg = [
            "",
            "-start",
            "p2a: Cinderace",
            "typechange",
            "Fighting",
            "[from] ability: Libero",
        ]
        start_volatile_status(self.battle, split_msg)

        self.assertEqual(["fighting"], self.battle.opponent.slot_a.active.types)

    def test_typechange_works_with_reflect_type(self):
        # |-start|p1a: Starmie|typechange|[from] move: Reflect Type|[of] p2a: Dragapult
        split_msg = [
            "",
            "-start",
            "p2a: Starmie",
            "typechange",
            "[from] move: Reflect Type",
            "[of] p1a: Dragapult",
        ]
        start_volatile_status(self.battle, split_msg)

        self.assertEqual(["dragon", "ghost"], self.battle.opponent.slot_a.active.types)

    def test_typechange_from_multiple_types(self):
        # |-start|p2a: Moltres|typechange|???/Flying|[from] move: Burn Up
        split_msg = [
            "",
            "-start",
            "p2a: Moltres",
            "typechange",
            "???/Flying",
            "[from] move: Burn Up",
        ]
        start_volatile_status(self.battle, split_msg)

        self.assertEqual(["???", "flying"], self.battle.opponent.slot_a.active.types)


class TestEndVolatileStatus(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active

        self.user_active = Pokemon("weedle", 100)
        self.battle.user.slot_a.active = self.user_active

    def test_removes_partiallytrapped(self):
        self.battle.opponent.slot_a.active.volatile_statuses = ["partiallytrapped"]
        split_msg = ["", "-end", "p2a: Caterpie", "whirlpool", "[partiallytrapped]"]
        end_volatile_status(self.battle, split_msg)

        self.assertEqual([], self.battle.opponent.slot_a.active.volatile_statuses)

    def test_removes_partiallytrapped_silent(self):
        self.battle.opponent.slot_a.active.volatile_statuses = ["partiallytrapped"]
        split_msg = [
            "",
            "-end",
            "p2a: Caterpie",
            "whirlpool",
            "[partiallytrapped]",
            "[silent]",
        ]
        end_volatile_status(self.battle, split_msg)

        self.assertEqual([], self.battle.opponent.slot_a.active.volatile_statuses)

    def test_removes_slowstart_volatile_duration(self):
        self.battle.opponent.slot_a.active.volatile_statuses = ["slowstart"]
        self.battle.opponent.slot_a.active.volatile_status_durations[
            constants.SLOW_START
        ] = 1
        split_msg = [
            "",
            "-end",
            "p2a: Caterpie",
            "Slow Start",
            "[silent]",
        ]
        end_volatile_status(self.battle, split_msg)

        self.assertEqual([], self.battle.opponent.slot_a.active.volatile_statuses)
        self.assertEqual(
            0,
            self.battle.opponent.slot_a.active.volatile_status_durations[
                constants.SLOW_START
            ],
        )

    def test_removes_taunt_volatile_duration(self):
        self.battle.opponent.slot_a.active.volatile_statuses = ["taunt"]
        self.battle.opponent.slot_a.active.volatile_status_durations[
            constants.TAUNT
        ] = 1
        split_msg = [
            "",
            "-end",
            "p2a: Caterpie",
            "Taunt",
            "[silent]",
        ]
        end_volatile_status(self.battle, split_msg)

        self.assertEqual([], self.battle.opponent.slot_a.active.volatile_statuses)
        self.assertEqual(
            0,
            self.battle.opponent.slot_a.active.volatile_status_durations[
                constants.TAUNT
            ],
        )

    def test_removes_yawn_volatile_duration(self):
        self.battle.opponent.slot_a.active.volatile_statuses = ["yawn"]
        self.battle.opponent.slot_a.active.volatile_status_durations[constants.YAWN] = 1
        split_msg = [
            "",
            "-end",
            "p2a: Caterpie",
            "Yawn",
            "[silent]",
        ]
        end_volatile_status(self.battle, split_msg)

        self.assertEqual([], self.battle.opponent.slot_a.active.volatile_statuses)
        self.assertEqual(
            0,
            self.battle.opponent.slot_a.active.volatile_status_durations[
                constants.YAWN
            ],
        )

    def test_removes_volatile_status_from_opponent(self):
        self.battle.opponent.slot_a.active.volatile_statuses = ["encore"]
        split_msg = ["", "-end", "p2a: Caterpie", "Encore"]
        end_volatile_status(self.battle, split_msg)

        expected_volatile_statuses = []

        self.assertEqual(
            expected_volatile_statuses,
            self.battle.opponent.slot_a.active.volatile_statuses,
        )

    def test_removes_protosynthesisspa_when_protocol_says_protosynthesis(self):
        self.battle.opponent.slot_a.active.volatile_statuses = ["protosynthesisspa"]
        split_msg = ["", "-end", "p2a: Caterpie", "Protosynthesis"]
        end_volatile_status(self.battle, split_msg)

        expected_volatile_statuses = []

        self.assertEqual(
            expected_volatile_statuses,
            self.battle.opponent.slot_a.active.volatile_statuses,
        )

    def test_removes_quarkdriveatk_when_protocol_says_quark_drive(self):
        self.battle.opponent.slot_a.active.volatile_statuses = ["quarkdriveatk"]
        split_msg = ["", "-end", "p2a: Caterpie", "Quark Drive"]
        end_volatile_status(self.battle, split_msg)

        expected_volatile_statuses = []

        self.assertEqual(
            expected_volatile_statuses,
            self.battle.opponent.slot_a.active.volatile_statuses,
        )

    def test_removes_volatile_status_from_user(self):
        self.battle.user.slot_a.active.volatile_statuses = ["encore"]
        split_msg = ["", "-end", "p1a: Weedle", "Encore"]
        end_volatile_status(self.battle, split_msg)

        expected_volatile_statuses = []

        self.assertEqual(
            expected_volatile_statuses, self.battle.user.slot_a.active.volatile_statuses
        )

    def test_halves_opponent_hp_when_dynamax_ends(self):
        self.battle.opponent.slot_a.active.volatile_statuses = ["dynamax"]
        hp, maxhp = (
            self.battle.opponent.slot_a.active.hp,
            self.battle.opponent.slot_a.active.max_hp,
        )
        split_msg = ["", "-end", "p2a: Weedle", "Dynamax"]
        end_volatile_status(self.battle, split_msg)

        self.assertEqual(hp / 2, self.battle.opponent.slot_a.active.hp)
        self.assertEqual(maxhp / 2, self.battle.opponent.slot_a.active.max_hp)

    def test_halves_bots_hp_when_dynamax_ends(self):
        self.battle.user.slot_a.active.volatile_statuses = ["dynamax"]
        hp, maxhp = (
            self.battle.user.slot_a.active.hp,
            self.battle.user.slot_a.active.max_hp,
        )
        split_msg = ["", "-end", "p1a: Weedle", "Dynamax"]
        end_volatile_status(self.battle, split_msg)

        self.assertEqual(hp / 2, self.battle.user.slot_a.active.hp)
        self.assertEqual(maxhp / 2, self.battle.user.slot_a.active.max_hp)

    def test_ending_substitute_sets_substitute_hit_to_false(self):
        self.battle.opponent.slot_a.active.substitute_hit = True

        split_msg = ["", "-end", "p2a: Weedle", "Substitute"]
        end_volatile_status(self.battle, split_msg)
        self.assertFalse(self.battle.opponent.slot_a.active.substitute_hit)


class TestUpdateAbility(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active
        self.battle.opponent.slot_a.active.ability = None

        self.user_active = Pokemon("weedle", 100)
        self.battle.user.slot_a.active = self.user_active

    def test_sets_as_one_spectrier(self):
        self.battle.opponent.slot_a.active.name = "calyrexshadow"
        split_msg = ["", "-ability", "p2a: Calyrex", "As One"]
        update_ability(self.battle, split_msg)
        self.assertEqual("asonespectrier", self.battle.opponent.slot_a.active.ability)

    def test_sets_as_one_glastrier(self):
        self.battle.opponent.slot_a.active.name = "calyrexice"
        split_msg = ["", "-ability", "p2a: Calyrex", "As One"]
        update_ability(self.battle, split_msg)
        self.assertEqual("asoneglastrier", self.battle.opponent.slot_a.active.ability)

    def test_does_not_update_asoneglastrier_to_unnerve(self):
        self.battle.opponent.slot_a.active.name = "calyrexice"
        split_msg = ["", "-ability", "p2a: Calyrex", "As One"]
        update_ability(self.battle, split_msg)
        split_msg = ["", "-ability", "p2a: Calyrex", "Unnerve"]
        update_ability(self.battle, split_msg)
        self.assertEqual("asoneglastrier", self.battle.opponent.slot_a.active.ability)

    def test_does_not_update_asonespectrier_to_unnerve(self):
        self.battle.opponent.slot_a.active.name = "calyrexshadow"
        split_msg = ["", "-ability", "p2a: Calyrex", "As One"]
        update_ability(self.battle, split_msg)
        split_msg = ["", "-ability", "p2a: Calyrex", "Unnerve"]
        update_ability(self.battle, split_msg)
        self.assertEqual("asonespectrier", self.battle.opponent.slot_a.active.ability)

    def test_sets_original_ability_from_trace(self):
        self.battle.user.slot_a.active.ability = "intimidate"
        self.battle.opponent.slot_a.active.ability = None

        split_msg = [
            "",
            "-ability",
            "p2a: Caterpie",
            "Intimidate",
            "[from] ability: Trace",
            "[of] p1a: Caterpie",
        ]
        update_ability(self.battle, split_msg)

        self.assertEqual("intimidate", self.battle.opponent.slot_a.active.ability)
        self.assertEqual("trace", self.battle.opponent.slot_a.active.original_ability)

    def test_sets_original_ability_from_trace_with_intimidate(self):
        self.battle.user.slot_a.active.ability = "intimidate"
        self.battle.opponent.slot_a.active.ability = None

        # PS protocol sends 2 `-ability` messages here so just make sure everything is set properly
        split_msg_1 = ["", "-ability", "p2a: Caterpie", "Intimidate", "boost"]
        split_msg_2 = [
            "",
            "-ability",
            "p2a: Caterpie",
            "Intimidate",
            "[from] ability: Trace",
            "[of] p1a: Caterpie",
        ]
        update_ability(self.battle, split_msg_1)
        update_ability(self.battle, split_msg_2)

        self.assertEqual("intimidate", self.battle.opponent.slot_a.active.ability)
        self.assertEqual("trace", self.battle.opponent.slot_a.active.original_ability)

    def test_update_ability_from_ability_string_properly_updates_ability(self):
        split_msg = ["", "-ability", "p2a: Caterpie", "Lightning Rod", "boost"]
        update_ability(self.battle, split_msg)

        expected_ability = "lightningrod"

        self.assertEqual(expected_ability, self.battle.opponent.slot_a.active.ability)

    def test_update_ability_from_ability_string_properly_updates_ability_for_bot(self):
        split_msg = ["", "-ability", "p1a: Caterpie", "Lightning Rod", "boost"]
        update_ability(self.battle, split_msg)

        expected_ability = "lightningrod"

        self.assertEqual(expected_ability, self.battle.user.slot_a.active.ability)


class TestSwapSideConditions(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active
        self.battle.opponent.slot_a.active.ability = None

        self.user_active = Pokemon("weedle", 100)
        self.battle.user.slot_a.active = self.user_active

    def get_expected_empty_dict(self):
        # The defaultdict's start empty, but swapping them adds the values of 0 to them
        return {k: 0 for k in constants.COURT_CHANGE_SWAPS}

    def test_does_nothing_when_no_side_conditions_are_present(self):
        split_msg = ["", "-swapsideconditions"]
        swapsideconditions(self.battle, split_msg)

        expected_dict = self.get_expected_empty_dict()

        self.assertEqual(expected_dict, self.battle.user.side_conditions)
        self.assertEqual(expected_dict, self.battle.opponent.side_conditions)

    def test_swaps_one_layer_of_spikes(self):
        split_msg = ["", "-swapsideconditions"]

        self.battle.user.side_conditions[constants.SPIKES] = 1

        swapsideconditions(self.battle, split_msg)

        expected_user_side_conditions = self.get_expected_empty_dict()

        expected_opponent_side_conditions = self.get_expected_empty_dict()
        expected_opponent_side_conditions[constants.SPIKES] = 1

        self.assertEqual(
            expected_user_side_conditions, self.battle.user.side_conditions
        )
        self.assertEqual(
            expected_opponent_side_conditions, self.battle.opponent.side_conditions
        )

    def test_swaps_one_layer_of_spikes_with_two_layers_of_spikes(self):
        split_msg = ["", "-swapsideconditions"]

        self.battle.user.side_conditions[constants.SPIKES] = 2
        self.battle.opponent.side_conditions[constants.SPIKES] = 1

        swapsideconditions(self.battle, split_msg)

        expected_user_side_conditions = self.get_expected_empty_dict()
        expected_user_side_conditions[constants.SPIKES] = 1

        expected_opponent_side_conditions = self.get_expected_empty_dict()
        expected_opponent_side_conditions[constants.SPIKES] = 2

        self.assertEqual(
            expected_user_side_conditions, self.battle.user.side_conditions
        )
        self.assertEqual(
            expected_opponent_side_conditions, self.battle.opponent.side_conditions
        )

    def test_swaps_multiple_side_conditions_on_either_side(self):
        split_msg = ["", "-swapsideconditions"]

        self.battle.user.side_conditions[constants.SPIKES] = 2
        self.battle.user.side_conditions[constants.REFLECT] = 3
        self.battle.user.side_conditions[constants.TAILWIND] = 2

        self.battle.opponent.side_conditions[constants.SPIKES] = 1
        self.battle.opponent.side_conditions[constants.LIGHT_SCREEN] = 2

        swapsideconditions(self.battle, split_msg)

        expected_user_side_conditions = self.get_expected_empty_dict()
        expected_user_side_conditions[constants.SPIKES] = 1
        expected_user_side_conditions[constants.LIGHT_SCREEN] = 2

        expected_opponent_side_conditions = self.get_expected_empty_dict()
        expected_opponent_side_conditions[constants.SPIKES] = 2
        expected_opponent_side_conditions[constants.REFLECT] = 3
        expected_opponent_side_conditions[constants.TAILWIND] = 2

        self.assertEqual(
            expected_user_side_conditions, self.battle.user.side_conditions
        )
        self.assertEqual(
            expected_opponent_side_conditions, self.battle.opponent.side_conditions
        )


class TestFaint(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active
        self.battle.opponent.slot_a.active.ability = None

        self.user_active_a = Pokemon("weedle", 100)
        self.user_active_b = Pokemon("Dondozo", 100)
        self.battle.user.slot_a.active = self.user_active_a
        self.battle.user.slot_b.active = self.user_active_b

    def test_fainting_with_commanded_removes_commanding_from_ally(self):
        self.battle.user.slot_a.active.volatile_statuses.append("commanding")
        self.battle.user.slot_b.active.volatile_statuses.append("commanded")
        split_msg = ["", "faint", "p1b: Dondozo"]
        faint(self.battle, split_msg)
        self.assertNotIn("commanding", self.battle.user.slot_a.active.volatile_statuses)


class TestFormChange(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active
        self.battle.opponent.slot_a.active.ability = None

        self.user_active = Pokemon("weedle", 100)
        self.battle.user.slot_a.active = self.user_active

    def test_changes_with_formechange_message(self):
        self.battle.opponent.slot_a.active = Pokemon("meloetta", 100)
        split_msg = [
            "",
            "-formechange",
            "p2a: Meloetta",
            "Meloetta - Pirouette",
            "[msg]",
        ]
        form_change(self.battle, split_msg)

        self.assertEqual("meloettapirouette", self.battle.opponent.slot_a.active.name)

    def test_preserves_boosts(self):
        self.battle.opponent.slot_a.active = Pokemon("meloetta", 100)
        self.battle.opponent.slot_a.active.boosts = {constants.ATTACK: 2}
        split_msg = [
            "",
            "-formechange",
            "p2a: Meloetta",
            "Meloetta - Pirouette",
            "[msg]",
        ]
        form_change(self.battle, split_msg)

        self.assertEqual(2, self.battle.opponent.slot_a.active.boosts[constants.ATTACK])

    def test_preserves_status(self):
        self.battle.opponent.slot_a.active = Pokemon("meloetta", 100)
        self.battle.opponent.slot_a.active.status = constants.BURN
        split_msg = [
            "",
            "-formechange",
            "p2a: Meloetta",
            "Meloetta - Pirouette",
            "[msg]",
        ]
        form_change(self.battle, split_msg)

        self.assertEqual(constants.BURN, self.battle.opponent.slot_a.active.status)

    def test_preserves_item(self):
        self.battle.opponent.slot_a.active = Pokemon("aegislash", 100)
        self.battle.opponent.slot_a.active.item = "airballoon"
        split_msg = [
            "",
            "-formechange",
            "p2a: Aegislash",
            "Aegislash-Blade",
            "[from] ability: Stance Change",
        ]
        form_change(self.battle, split_msg)

        self.assertEqual("airballoon", self.battle.opponent.slot_a.active.item)

    def test_preserves_base_name_when_form_changes(self):
        self.battle.opponent.slot_a.active = Pokemon("meloetta", 100)
        split_msg = [
            "",
            "-formechange",
            "p2a: Meloetta",
            "Meloetta - Pirouette",
            "[msg]",
        ]
        form_change(self.battle, split_msg)

        self.assertEqual("meloetta", self.battle.opponent.slot_a.active.base_name)

    def test_multiple_forme_changes_does_not_ruin_base_name(self):
        self.battle.user.slot_a.active = Pokemon("pikachu", 100)
        self.battle.opponent.slot_a.active = Pokemon("pikachu", 100)
        self.battle.opponent.reserve = []
        self.battle.opponent.reserve.append(Pokemon("wishiwashi", 100))

        m1 = ["", "switch", "p2a: Wishiwashi", "Wishiwashi, L100, M", "100/100"]
        m2 = [
            "",
            "-formechange",
            "p2a: Wishiwashi",
            "Wishiwashi-School",
            "",
            "[from] ability: Schooling",
        ]
        m3 = ["", "switch", "p2a: Pikachu", "Pikachu, L100, M", "100/100"]
        m4 = ["", "switch", "p2a: Wishiwashi", "Wishiwashi, L100, M", "100/100"]
        m5 = [
            "",
            "-formechange",
            "p2a: Wishiwashi",
            "Wishiwashi-School",
            "",
            "[from] ability: Schooling",
        ]
        m6 = ["", "switch", "p2a: Pikachu", "Pikachu, L100, M", "100/100"]
        m7 = ["", "switch", "p2a: Wishiwashi", "Wishiwashi, L100, M", "100/100"]
        m8 = [
            "",
            "-formechange",
            "p2a: Wishiwashi",
            "Wishiwashi-School",
            "",
            "[from] ability: Schooling",
        ]

        switch_or_drag(self.battle, m1)
        form_change(self.battle, m2)
        switch_or_drag(self.battle, m3)
        switch_or_drag(self.battle, m4)
        form_change(self.battle, m5)
        switch_or_drag(self.battle, m6)
        switch_or_drag(self.battle, m7)
        form_change(self.battle, m8)

        pkmn = Pokemon("wishiwashischool", 100)
        self.assertNotIn(pkmn, self.battle.opponent.reserve)


class TestClearNegativeBoost(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.user_active = Pokemon("weedle", 100)
        self.battle.user.slot_a.active = self.user_active

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active

    def test_clears_negative_boosts(self):
        self.battle.opponent.slot_a.active.boosts = {constants.ATTACK: -1}
        split_msg = ["", "-clearnegativeboost", "p2a: caterpie", "[silent]"]
        clearnegativeboost(self.battle, split_msg)

        self.assertEqual(0, self.battle.opponent.slot_a.active.boosts[constants.ATTACK])

    def test_clears_multiple_negative_boosts(self):
        self.battle.opponent.slot_a.active.boosts = {
            constants.ATTACK: -1,
            constants.SPEED: -1,
        }
        split_msg = ["", "-clearnegativeboost", "p2a: caterpie", "[silent]"]
        clearnegativeboost(self.battle, split_msg)

        self.assertEqual(0, self.battle.opponent.slot_a.active.boosts[constants.ATTACK])
        self.assertEqual(0, self.battle.opponent.slot_a.active.boosts[constants.SPEED])

    def test_does_not_clear_positive_boost(self):
        self.battle.opponent.slot_a.active.boosts = {constants.ATTACK: 1}
        split_msg = ["", "-clearnegativeboost", "p2a: caterpie", "[silent]"]
        clearnegativeboost(self.battle, split_msg)

        self.assertEqual(1, self.battle.opponent.slot_a.active.boosts[constants.ATTACK])

    def test_clears_only_negative_boosts(self):
        self.battle.opponent.slot_a.active.boosts = {
            constants.ATTACK: 1,
            constants.SPECIAL_ATTACK: 1,
            constants.SPEED: 1,
            constants.DEFENSE: -1,
            constants.SPECIAL_DEFENSE: -1,
        }
        split_msg = ["", "-clearnegativeboost", "p2a: caterpie", "[silent]"]
        clearnegativeboost(self.battle, split_msg)

        expected_boosts = {
            constants.ATTACK: 1,
            constants.SPECIAL_ATTACK: 1,
            constants.SPEED: 1,
            constants.DEFENSE: 0,
            constants.SPECIAL_DEFENSE: 0,
        }

        self.assertEqual(expected_boosts, self.battle.opponent.slot_a.active.boosts)


class TestClearBoost(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.user_active = Pokemon("weedle", 100)
        self.battle.user.slot_a.active = self.user_active

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active

    def test_clears_boost(self):
        self.battle.opponent.slot_a.active.boosts = {constants.ATTACK: 2}
        split_msg = ["", "-clearboost", "p2a: caterpie", "[silent]"]
        clearboost(self.battle, split_msg)

        self.assertEqual(0, self.battle.opponent.slot_a.active.boosts[constants.ATTACK])

    def test_clears_multiple_boosts(self):
        self.battle.opponent.slot_a.active.boosts = {
            constants.ATTACK: 2,
            constants.SPEED: 1,
            constants.SPECIAL_ATTACK: -3,
        }
        split_msg = ["", "-clearboost", "p2a: caterpie", "[silent]"]
        clearboost(self.battle, split_msg)

        self.assertEqual(0, self.battle.opponent.slot_a.active.boosts[constants.ATTACK])
        self.assertEqual(
            0, self.battle.opponent.slot_a.active.boosts[constants.SPECIAL_ATTACK]
        )
        self.assertEqual(0, self.battle.opponent.slot_a.active.boosts[constants.SPEED])


class TestSideStart(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active
        self.battle.opponent.slot_a.active.ability = None
        self.battle.opponent.slot_b.active = Pokemon("beedrill", 100)

        self.user_active = Pokemon("weedle", 100)
        self.battle.user.slot_a.active = self.user_active
        self.battle.user.slot_b.active = Pokemon("beedrill", 100)

        self.username = "CoolUsername"

        self.battle.username = self.username

    def test_stealthrock_gets_1_layer(self):
        split_msg = ["", "-sidestart", "p2", "Stealth Rock"]
        sidestart(self.battle, split_msg)
        self.assertEqual(
            1, self.battle.opponent.side_conditions[constants.STEALTH_ROCK]
        )

    def test_spikes_increments_by_1(self):
        split_msg = ["", "-sidestart", "p2", "Spikes"]
        self.battle.opponent.side_conditions[constants.SPIKES] = 1
        sidestart(self.battle, split_msg)
        self.assertEqual(2, self.battle.opponent.side_conditions[constants.SPIKES])

    def test_reflect_gets_5_turns(self):
        split_msg = ["", "-sidestart", "p2", "Reflect"]
        sidestart(self.battle, split_msg)
        self.assertEqual(5, self.battle.opponent.side_conditions[constants.REFLECT])

    def test_lightscreen_gets_5_turns(self):
        split_msg = ["", "-sidestart", "p2", "move: Light Screen"]
        sidestart(self.battle, split_msg)
        self.assertEqual(
            5, self.battle.opponent.side_conditions[constants.LIGHT_SCREEN]
        )

    def test_lightscreen_gets_8_turns_with_lightclay(self):
        split_msg = ["", "-sidestart", "p2", "move: Light Screen"]
        self.battle.opponent.slot_a.active.item = "lightclay"
        sidestart(self.battle, split_msg)
        self.assertEqual(
            8, self.battle.opponent.side_conditions[constants.LIGHT_SCREEN]
        )

    def test_auroraveil_gets_8_turns_with_lightclay(self):
        split_msg = ["", "-sidestart", "p2", "move: Aurora Veil"]
        self.battle.opponent.slot_a.active.item = "lightclay"
        sidestart(self.battle, split_msg)
        self.assertEqual(8, self.battle.opponent.side_conditions[constants.AURORA_VEIL])

    def test_tailwind_gets_4_turns(self):
        split_msg = ["", "-sidestart", "p2", "move: Tail Wind"]
        sidestart(self.battle, split_msg)
        self.assertEqual(4, self.battle.opponent.side_conditions[constants.TAILWIND])


class TestSingleTurn(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active
        self.battle.opponent.slot_a.active.ability = None

        self.user_active = Pokemon("weedle", 100)
        self.battle.user.slot_a.active = self.user_active

        self.username = "CoolUsername"

        self.battle.username = self.username

    def test_sets_protect_side_condition_for_opponent_when_used(self):
        split_msg = ["", "-singleturn", "p2a: Caterpie", "Protect"]
        singleturn(self.battle, split_msg)

        self.assertEqual(
            2,
            self.battle.opponent.slot_a.active.volatile_status_durations[
                constants.PROTECT
            ],
        )

    def test_sets_helpinghand_from_singleturn(self):
        # |-singleturn|p2b: Garchomp|Helping Hand|[of] p2a: Torkoal
        split_msg = ["", "-singleturn", "p2a: Caterpie", "Helping Hand", "p2b: Weedle"]
        singleturn(self.battle, split_msg)

        self.assertIn(
            "helpinghand", self.battle.opponent.slot_a.active.volatile_statuses
        )

    def test_sets_protect_side_condition_when_endure_is_used(self):
        split_msg = ["", "-singleturn", "p2a: Caterpie", "Endure"]
        singleturn(self.battle, split_msg)

        self.assertEqual(
            2,
            self.battle.opponent.slot_a.active.volatile_status_durations[
                constants.PROTECT
            ],
        )

    def test_does_not_set_for_non_protect_move(self):
        split_msg = ["", "-singleturn", "p2a: Caterpie", "Roost"]
        singleturn(self.battle, split_msg)

        self.assertEqual(0, self.battle.opponent.side_conditions[constants.PROTECT])

    def test_sets_protect_side_condition_for_bot_when_used(self):
        split_msg = ["", "-singleturn", "p1a: Weedle", "Protect"]
        singleturn(self.battle, split_msg)

        self.assertEqual(
            2,
            self.battle.user.slot_a.active.volatile_status_durations[constants.PROTECT],
        )

    def test_sets_protect_side_condition_when_prefixed_by_move(self):
        split_msg = ["", "-singleturn", "p2a: Caterpie", "move: Protect"]
        singleturn(self.battle, split_msg)

        self.assertEqual(
            2,
            self.battle.opponent.slot_a.active.volatile_status_durations[
                constants.PROTECT
            ],
        )


class TestCant(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active

        self.user_active = Pokemon("weedle", 100)
        self.battle.user.slot_a.active = self.user_active

    def test_increments_sleep_turns_when_cant_from_sleep(self):
        self.battle.user.slot_a.active.sleep_turns = 0
        self.battle.user.slot_a.active.status = constants.SLEEP
        cant(self.battle, ["", "-cant", "p1a: Weedle", "slp"])
        self.assertEqual(1, self.battle.user.slot_a.active.sleep_turns)

    def test_removes_truant_when_cant_from_truant(self):
        self.battle.user.slot_a.active.sleep_turns = 0
        self.battle.user.slot_a.active.volatile_statuses.append("truant")
        cant(self.battle, ["", "-cant", "p1a: Slaking", "ability: Truant"])
        self.assertNotIn("truant", self.battle.user.slot_a.active.volatile_statuses)

    def test_removes_mustrecharge_when_cant_from_recharge(self):
        self.battle.user.slot_a.active.sleep_turns = 0
        self.battle.user.slot_a.active.volatile_statuses.append("mustrecharge")
        cant(self.battle, ["", "-cant", "p1a: Slaking", "recharge"])
        self.assertNotIn(
            "mustrecharge", self.battle.user.slot_a.active.volatile_statuses
        )

    def test_only_decrements_rest_turns_when_cant_from_sleep_with_a_rest_turn(self):
        self.battle.user.slot_a.active.sleep_turns = 0
        self.battle.user.slot_a.active.rest_turns = 3
        self.battle.user.slot_a.active.status = constants.SLEEP
        cant(self.battle, ["", "-cant", "p1a: Weedle", "slp"])
        self.assertEqual(0, self.battle.user.slot_a.active.sleep_turns)
        self.assertEqual(2, self.battle.user.slot_a.active.rest_turns)


class TestUpkeep(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active
        self.battle.opponent.slot_b.active = Pokemon("beedrill", 100)

        self.user_active = Pokemon("weedle", 100)
        self.battle.user.slot_a.active = self.user_active
        self.battle.user.slot_b.active = Pokemon("beedrill", 100)

    def test_removes_helping_hand(self):
        self.battle.user.slot_a.active.volatile_statuses.append("helpinghand")
        self.assertIn("helpinghand", self.battle.user.slot_a.active.volatile_statuses)
        upkeep(self.battle, "")
        self.assertNotIn(
            "helpinghand", self.battle.user.slot_a.active.volatile_statuses
        )

    def test_decrements_slowstart_volatile_duration(self):
        self.battle.user.slot_a.active.volatile_statuses.append(constants.SLOW_START)
        self.battle.user.slot_a.active.volatile_status_durations[
            constants.SLOW_START
        ] = 5
        upkeep(self.battle, "")
        self.assertEqual(
            4,
            self.battle.user.slot_a.active.volatile_status_durations[
                constants.SLOW_START
            ],
        )

    def test_increments_lockedmove_end_of_turn(self):
        self.battle.opponent.slot_a.active.volatile_statuses.append(
            constants.LOCKED_MOVE
        )
        self.battle.opponent.slot_a.active.volatile_status_durations[
            constants.LOCKED_MOVE
        ] = 0
        upkeep(self.battle, "")
        self.assertEqual(
            1,
            self.battle.opponent.slot_a.active.volatile_status_durations[
                constants.LOCKED_MOVE
            ],
        )

    def test_decrements_reflect_end_of_turn(self):
        self.battle.opponent.side_conditions[constants.REFLECT] = 5
        upkeep(self.battle, "")
        self.assertEqual(4, self.battle.opponent.side_conditions[constants.REFLECT])

    def test_decrementing_reflect_to_0_extends_by_3(self):
        self.battle.opponent.side_conditions[constants.REFLECT] = 1
        upkeep(self.battle, "")
        self.assertEqual(3, self.battle.opponent.side_conditions[constants.REFLECT])

    def test_decrements_lightscreen_end_of_turn(self):
        self.battle.opponent.side_conditions[constants.LIGHT_SCREEN] = 5
        upkeep(self.battle, "")
        self.assertEqual(
            4, self.battle.opponent.side_conditions[constants.LIGHT_SCREEN]
        )

    def test_decrementing_lightscreen_to_0_extends_by_3(self):
        self.battle.opponent.side_conditions[constants.LIGHT_SCREEN] = 1
        upkeep(self.battle, "")
        self.assertEqual(
            3, self.battle.opponent.side_conditions[constants.LIGHT_SCREEN]
        )

    def test_decrements_auroraveil_end_of_turn(self):
        self.battle.opponent.side_conditions[constants.AURORA_VEIL] = 5
        upkeep(self.battle, "")
        self.assertEqual(4, self.battle.opponent.side_conditions[constants.AURORA_VEIL])

    def test_decrementing_auroraveil_to_0_extends_by_3(self):
        self.battle.opponent.side_conditions[constants.AURORA_VEIL] = 1
        upkeep(self.battle, "")
        self.assertEqual(3, self.battle.opponent.side_conditions[constants.AURORA_VEIL])

    def test_decrements_tailwind_end_of_turn(self):
        self.battle.opponent.side_conditions[constants.TAILWIND] = 2
        upkeep(self.battle, "")
        self.assertEqual(1, self.battle.opponent.side_conditions[constants.TAILWIND])

    def test_field_turns_remaining_is_decremented(self):
        self.battle.field_turns_remaining = 5
        self.battle.field = constants.GRASSY_TERRAIN
        upkeep(self.battle, "")
        self.assertEqual(4, self.battle.field_turns_remaining)

    def test_0_turns_remaining_field_sets_turns_remaining_to_3(self):
        self.battle.field_turns_remaining = 1
        self.battle.field = constants.GRASSY_TERRAIN
        upkeep(self.battle, "")
        self.assertEqual(3, self.battle.field_turns_remaining)

    def test_none_field_does_not_change_field_or_turns_remaining(self):
        self.battle.field_turns_remaining = 0
        self.battle.field = None
        upkeep(self.battle, "")
        self.assertEqual(0, self.battle.field_turns_remaining)

    def test_increments_yawn_duration(self):
        self.battle.user.slot_a.active.volatile_statuses.append(constants.YAWN)
        upkeep(self.battle, "")
        self.assertEqual(
            1, self.battle.user.slot_a.active.volatile_status_durations[constants.YAWN]
        )

    def test_decrements_trickroom_in_upkeep(self):
        self.battle.trick_room = True
        self.battle.trick_room_turns_remaining = 5
        upkeep(self.battle, "")
        self.assertEqual(4, self.battle.trick_room_turns_remaining)

    def test_swaps_out_yawn_for_yawnSleepThisTurn_opponent(self):
        self.battle.opponent.slot_a.active.volatile_statuses.append(constants.YAWN)
        self.battle.opponent.slot_a.active.volatile_status_durations[constants.YAWN] = 0
        upkeep(self.battle, "")
        self.assertIn(
            constants.YAWN,
            self.battle.opponent.slot_a.active.volatile_statuses,
        )
        self.assertEqual(
            1,
            self.battle.opponent.slot_a.active.volatile_status_durations[
                constants.YAWN
            ],
        )

    def test_removes_yawnSleepNextTurn(self):
        self.battle.user.slot_a.active.volatile_statuses.append(constants.YAWN)
        self.battle.user.slot_a.active.volatile_status_durations[constants.YAWN] = 1
        upkeep(self.battle, "")
        self.assertEqual(
            0, self.battle.user.slot_a.active.volatile_status_durations[constants.YAWN]
        )
        self.assertNotIn(
            constants.YAWN, self.battle.user.slot_a.active.volatile_statuses
        )

    def test_reduces_protect_for_bot(self):
        self.battle.user.side_conditions[constants.PROTECT] = 1

        upkeep(self.battle, "")

        self.assertEqual(
            self.battle.user.slot_a.active.volatile_status_durations[constants.PROTECT],
            0,
        )

    def test_does_not_reduce_protect_when_it_is_0(self):
        self.battle.user.side_conditions[constants.PROTECT] = 0

        upkeep(self.battle, "")

        self.assertEqual(self.battle.user.side_conditions[constants.PROTECT], 0)

    def test_does_not_reduce_wish_if_it_is_0(self):
        self.battle.user.wish = (0, 100)

        upkeep(self.battle, "")

        self.assertEqual(self.battle.user.wish, (0, 100))


class TestCheckSpeedRanges(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active_a = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active_a
        self.battle.opponent.slot_a.active.ability = None

        self.opponent_active_b = Pokemon("weedle", 100)
        self.battle.opponent.slot_b.active = self.opponent_active_b
        self.battle.opponent.slot_b.active.ability = None

        self.user_active_a = Pokemon("caterpie", 100)
        self.battle.user.slot_a.active = self.user_active_a

        self.user_active_b = Pokemon("weedle", 100)
        self.battle.user.slot_b.active = self.user_active_b

        self.username = "CoolUsername"
        self.battle.username = self.username

        self.battle.request_json = {
            constants.ACTIVE: [{constants.MOVES: []}],
            constants.SIDE: {
                constants.ID: None,
                constants.NAME: None,
                constants.POKEMON: [],
                constants.RQID: None,
            },
        }

    def test_tailwind_splitting_speed_range(self):
        self.battle.user.name = "p2"
        self.battle.opponent.name = "p1"
        self.battle.msg_list = [
            "|-terastallize|p1a: Ursaluna|Normal",
            "|move|p1b: Talonflame|Tailwind|p1b: Talonflame",
            "|-sidestart|p1: 1.65meters|move: Tailwind",
            "|move|p1a: Ursaluna|Blood Moon|p2a: Ninetales",
            "|-damage|p2a: Ninetales|0 fnt",
            "|faint|p2a: Ninetales",
            "|-damage|p1a: Ursaluna|91/100|[from] item: Life Orb",
            "|move|p2b: Garchomp|Rock Slide|p1b: Talonflame|[spread] p1a,p1b",
            "|-supereffective|p1b: Talonflame",
            "|-damage|p1a: Ursaluna|68/100",
            "|-damage|p1b: Talonflame|0 fnt",
            "|faint|p1b: Talonflame",
        ]
        # tailwind ursaluna must have at least 50 speed
        # since it went before garchomp with 100 speed
        self.battle.user.slot_b.active.stats[constants.SPEED] = 100
        process_battle_updates(self.battle)
        self.assertEqual(50, self.battle.opponent.slot_a.active.speed_range.min)

    def test_rain_activating_when_someone_has_swiftswim_splitting_speed_range(self):
        self.battle.user.name = "p2"
        self.battle.opponent.name = "p1"
        self.battle.opponent.slot_a.active.ability = "swiftswim"
        self.battle.msg_list = [
            "|-terastallize|p1a: Ursaluna|Normal",
            "|switch|p1b: Pelipper|Pelipper, L50, M|100/100",
            "|-weather|RainDance|[from] ability: Drizzle|[of] p1a: Pelipper",
            "|move|p1a: Ursaluna|Blood Moon|p2a: Ninetales",
            "|-damage|p2a: Ninetales|0 fnt",
            "|faint|p2a: Ninetales",
            "|-damage|p1a: Ursaluna|91/100|[from] item: Life Orb",
            "|move|p2b: Garchomp|Rock Slide|p1b: Talonflame|[spread] p1a,p1b",
            "|-supereffective|p1b: Talonflame",
            "|-damage|p1a: Ursaluna|68/100",
            "|-damage|p1b: Talonflame|0 fnt",
            "|faint|p1b: Talonflame",
        ]
        # swiftswim on ursaluna must have at least 50 speed
        # since it went before garchomp with 100 speed
        self.battle.user.slot_b.active.stats[constants.SPEED] = 100
        process_battle_updates(self.battle)
        self.assertEqual(50, self.battle.opponent.slot_a.active.speed_range.min)

    def test_does_not_infer_if_bot_moved_and_then_fainted(
        self,
    ):
        self.battle.msg_list = [
            "|move|p1a: Ursaluna|Tackle|p2a: Incineroar",
            "|move|p2a: Incineroar|Tackle|p1a: Ursaluna",
            "|-damage|p1a: Ursaluna|0/100 brn",
            "|faint|p1a: Ursaluna",
        ]
        self.battle.turn = 1
        self.battle.user.slot_a.last_selected_move = LastUsedMove(
            pokemon_name="ursaluna", move="tackle", turn=1
        )
        self.battle.user.slot_a.active.stats[constants.SPEED] = 100
        process_battle_updates(self.battle)
        self.assertEqual(0, self.battle.opponent.slot_a.active.speed_range.min)
        self.assertEqual(100, self.battle.opponent.slot_a.active.speed_range.max)

    def test_bots_pokemon_fainting_before_moving_sets_min_speed_on_opponents_when_priorities_are_the_same(
        self,
    ):
        self.battle.msg_list = [
            "|move|p2a: Incineroar|Tackle|p1b: Ursaluna",
            "|-damage|p1a: Ursaluna|0/100 brn",
            "|faint|p1a: Ursaluna",
        ]
        self.battle.turn = 1
        self.battle.user.slot_a.last_selected_move = LastUsedMove(
            pokemon_name="ursaluna", move="tackle", turn=1
        )
        self.battle.user.slot_a.active.stats[constants.SPEED] = 100
        process_battle_updates(self.battle)
        self.assertEqual(100, self.battle.opponent.slot_a.active.speed_range.min)

    def test_choicescarf_impacts_speed_range(
        self,
    ):
        self.battle.msg_list = [
            "|move|p2a: Incineroar|Tackle|p1b: Ursaluna",
            "|-damage|p1a: Ursaluna|0/100 brn",
            "|faint|p1a: Ursaluna",
        ]
        self.battle.turn = 1
        self.battle.opponent.slot_a.active.item = "choicescarf"
        self.battle.user.slot_a.last_selected_move = LastUsedMove(
            pokemon_name="ursaluna", move="tackle", turn=1
        )
        self.battle.user.slot_a.active.stats[constants.SPEED] = 100
        process_battle_updates(self.battle)
        self.assertEqual(
            int(100 / 1.5), self.battle.opponent.slot_a.active.speed_range.min
        )

    def test_bot_fainted_can_infer_multiple_speed_ranges(
        self,
    ):
        self.battle.user.slot_a.active.name = "ursaluna"
        self.battle.opponent.slot_a.active.name = "incineroar"
        self.battle.opponent.slot_b.active.name = "sneasler"
        self.battle.msg_list = [
            "|move|p2a: Incineroar|Tackle|p1b: Ursaluna",
            "|move|p2b: Sneasler|Dire Claw|p1b: Ursaluna",
            "|-damage|p1a: Ursaluna|0/100 brn",
            "|faint|p1a: Ursaluna",
        ]
        self.battle.turn = 1
        self.battle.user.slot_a.last_selected_move = LastUsedMove(
            pokemon_name="ursaluna", move="tackle", turn=1
        )
        self.battle.user.slot_a.active.stats[constants.SPEED] = 100
        process_battle_updates(self.battle)
        self.assertEqual(100, self.battle.opponent.slot_a.active.speed_range.min)
        self.assertEqual(100, self.battle.opponent.slot_b.active.speed_range.min)

    def test_does_not_infer_from_faint_when_move_was_after_faint_msg(
        self,
    ):
        self.battle.msg_list = [
            "|move|p2a: Incineroar|Tackle|p1b: Ursaluna",
            "|-damage|p1a: Ursaluna|0/100 brn",
            "|faint|p1a: Ursaluna",
            "|move|p2b: Caterpie|Tackle|p1a: Weedle",
        ]
        self.battle.turn = 1
        self.battle.user.slot_a.last_selected_move = LastUsedMove(
            pokemon_name="ursaluna", move="tackle", turn=1
        )
        self.battle.user.slot_a.active.stats[constants.SPEED] = 100
        process_battle_updates(self.battle)
        self.assertEqual(100, self.battle.opponent.slot_a.active.speed_range.min)
        self.assertEqual(0, self.battle.opponent.slot_b.active.speed_range.min)

    def test_does_not_infer_speed_if_fainted_after_switching(self):
        self.battle.msg_list = [
            "|switch|p1a: Ursaluna|Ursaluna, L50, M|100/100",
            "|move|p2a: Incineroar|Tackle|p1b: Ursaluna",
            "|-damage|p1a: Ursaluna|0/100 brn",
            "|faint|p1a: Ursaluna",
        ]
        self.battle.turn = 1
        self.battle.user.slot_a.last_selected_move = LastUsedMove(
            pokemon_name="ursaluna", move="switch ursaluna", turn=1
        )
        self.battle.user.slot_a.active.stats[constants.SPEED] = 100
        process_battle_updates(self.battle)
        self.assertEqual(0, self.battle.opponent.slot_b.active.speed_range.min)

    def test_bot_side_getting_cant_can_be_used_to_infer_faster_than(self):
        self.battle.msg_list = [
            "|move|p2a: Incineroar|Fake Out|p1b: Ursaluna",
            "|-damage|p1a: Ursaluna|82/100 brn",
            # The order of the next two reveals speed ranges
            # p2a is faster than p1b
            "|move|p2b: Archaludon|Tackle|p1a: Ursaluna",
            "|cant|p1a: Ursaluna|flinch",
        ]
        self.battle.turn = 1
        self.battle.user.slot_a.last_selected_move = LastUsedMove(
            pokemon_name="ursaluna", move="tackle", turn=1
        )
        self.battle.user.slot_a.active.stats[constants.SPEED] = 100
        process_battle_updates(self.battle)
        self.assertEqual(100, self.battle.opponent.slot_b.active.speed_range.min)

    def test_bot_using_priority_move_but_getting_flinched(self):
        self.battle.msg_list = [
            "|move|p2a: Incineroar|Fake Out|p1b: Ursaluna",
            "|-damage|p1a: Ursaluna|82/100 brn",
            "|cant|p1a: Ursaluna|flinch",  # this was trying to use fakeout, meaning p2a is faster than p1a
            "|move|p2a: Archaludon|Tackle|p1a: Ursaluna",
        ]
        self.battle.turn = 1
        self.battle.user.slot_a.last_selected_move = LastUsedMove(
            pokemon_name="ursaluna", move="fakeout", turn=1
        )
        self.battle.user.slot_a.active.stats[constants.SPEED] = 100
        process_battle_updates(self.battle)
        self.assertEqual(100, self.battle.opponent.slot_a.active.speed_range.min)

    def test_bot_side_getting_cant_can_be_used_to_infer_slower_than(self):
        self.battle.msg_list = [
            "|move|p2a: Incineroar|Fake Out|p1b: Ursaluna",
            "|-damage|p1a: Ursaluna|82/100 brn",
            "|cant|p1a: Ursaluna|flinch",  # this was trying to use tackle, meaning p1a is faster than p2b
            "|move|p2b: Archaludon|Tackle|p1a: Ursaluna",
        ]
        self.battle.turn = 1
        self.battle.user.slot_a.last_selected_move = LastUsedMove(
            pokemon_name="ursaluna", move="tackle", turn=1
        )
        self.battle.user.slot_a.active.stats[constants.SPEED] = 100
        process_battle_updates(self.battle)
        self.assertEqual(100, self.battle.opponent.slot_b.active.speed_range.max)

    def test_opponent_side_getting_cant_does_not_reveal_speed_range(self):
        self.battle.msg_list = [
            "|move|p1a: Incineroar|Fake Out|p2b: Ursaluna",
            "|-damage|p2a: Ursaluna|82/100 brn",
            "|cant|p2a: Ursaluna|flinch",  # we can't infer anything here, because we don't know what move the opponent was trying to use
            "|move|p1b: Archaludon|Tackle|p2a: Ursaluna",
        ]
        self.battle.turn = 1
        self.battle.user.slot_a.active.stats[constants.SPEED] = 100
        process_battle_updates(self.battle)
        self.assertEqual(
            float("inf"), self.battle.opponent.slot_b.active.speed_range.max
        )
        self.assertEqual(0, self.battle.opponent.slot_b.active.speed_range.min)

    def test_switch_and_fakeout_still_allow_other_two_speeds_to_be_checked(self):
        self.battle.msg_list = [
            # p1 switching
            "|switch|p1b: Archaludon|Archaludon, L50, M|100/100",
            # p2 using priority move
            "|move|p2b: Incineroar|Fake Out|p1b: Archaludon",
            # p1a using 0 priority move
            "|move|p1a: Maushold|Population Bomb|p1b: Archaludon",
            # p2a using 0 priority move means p1a should have min speed set to p2a
            "|move|p2a: Ursaluna|Blood Moon|p1a: Maushold",
        ]
        self.battle.user.name = "p2"
        self.battle.opponent.name = "p1"
        self.battle.user.slot_a.active.stats[constants.SPEED] = 100
        process_battle_updates(self.battle)
        self.assertEqual(100, self.battle.opponent.slot_a.active.speed_range.min)

    def test_protosynthesis_speed_is_accounted_for_in_speed_range_check(self):
        self.battle.user.slot_a.active.stats[constants.SPEED] = 300
        self.battle.user.slot_a.active.boosts[constants.SPEED] = 1
        self.battle.user.last_selected_move = LastUsedMove("caterpie", "tackle", 0)

        self.battle.opponent.slot_a.active.stats[constants.SPEED] = 370
        self.battle.opponent.slot_a.active.volatile_statuses.append("protosynthesisspe")

        self.battle.msg_list = [
            "|move|p2a: Pikachu|U-turn|p1a: Caterpie",
            "|move|p1a: Caterpie|Tackle|p1a: Caterpie",
            "|faint|p2a: Caterpie",
        ]
        process_battle_updates(self.battle)
        self.assertEqual(
            300, self.battle.opponent.slot_a.active.speed_range.min
        )  # unchanged

    def test_recharging_makes_this_check_not_happen(self):
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.opponent.slot_a.active.stats[constants.SPEED] = 100
        self.battle.user.last_selected_move = LastUsedMove("caterpie", "agility", 0)

        self.battle.msg_list = [
            "|cant|p1a: Caterpie|recharge",
            "|move|p2a: Pikachu|Tackle|p1a: Caterpie",
            "|-damage|p1a: Caterpie|1/100",
            "|upkeep",
            "|turn|7",
        ]
        process_battle_updates(self.battle)
        self.assertEqual(
            0, self.battle.opponent.slot_a.active.speed_range.min
        )  # unchanged

    def test_hit_self_in_confusion_makes_this_check_not_happen(self):
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.opponent.slot_a.active.stats[constants.SPEED] = 100
        self.battle.user.last_selected_move = LastUsedMove("caterpie", "agility", 0)

        self.battle.msg_list = [
            "|-activate|p1a: Caterpie|confusion",
            "|-damage|p1a: Caterpie|15/100|[from] confusion",
            "|move|p2a: Pikachu|Tackle|p1a: Caterpie",
            "|-damage|p1a: Caterpie|1/100",
            "|upkeep",
            "|turn|7",
        ]
        process_battle_updates(self.battle)
        self.assertEqual(
            0, self.battle.opponent.slot_a.active.speed_range.min
        )  # unchanged

    def test_boosting_speed_after_opponent_does_not_mess_up_speed_range_check(self):
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.opponent.slot_a.active.stats[constants.SPEED] = 100
        self.battle.user.last_selected_move = LastUsedMove("caterpie", "agility", 0)

        self.battle.msg_list = [
            "|move|p2a: Pikachu|Tackle|p1a: Caterpie",
            "|-damage|p1a: Caterpie|1/100",
            "|move|p1a: Caterpie|Agility|p1a: Caterpie",
            "|-boost|p1a: Caterpie|spe|2",
            "|upkeep",
            "|turn|7",
        ]
        process_battle_updates(self.battle)
        self.assertEqual(150, self.battle.opponent.slot_a.active.speed_range.min)

    def test_boosting_speed_before_opponent_does_not_mess_up_speed_range_check(self):
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.opponent.slot_a.active.stats[constants.SPEED] = 100
        self.battle.user.last_selected_move = LastUsedMove("caterpie", "agility", 0)

        self.battle.msg_list = [
            "|move|p1a: Caterpie|Agility|p1a: Caterpie",
            "|-boost|p1a: Caterpie|spe|2",
            "|move|p2a: Pikachu|Tackle|p1a: Caterpie",
            "|-damage|p1a: Caterpie|1/100",
            "|upkeep",
            "|turn|7",
        ]
        process_battle_updates(self.battle)
        self.assertEqual(150, self.battle.opponent.slot_a.active.speed_range.max)

    def test_user_knocking_out_opponent_does_nothing(
        self,
    ):
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.opponent.slot_a.active.stats[constants.SPEED] = 100
        self.battle.user.last_selected_move = LastUsedMove("caterpie", "tackle", 0)

        self.battle.msg_list = [
            "|move|p1a: Caterpie|Tackle|p2a: Pikachu",
            "|-damage|p2a: Pikachu|0 fnt",
            "|faint|p2a: Pikachu",
            "|upkeep",
            "|turn|7",
        ]
        process_battle_updates(self.battle)
        self.assertEqual(0, self.battle.opponent.slot_a.active.speed_range.min)

    def test_suckerpunch_and_thunderclap_sets_speed_ranges(self):
        # opponent should have min speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.opponent.slot_a.active.stats[constants.SPEED] = 175

        self.battle.msg_list = [
            "|move|p2a: Raging Bolt|Thunderclap|p1a: Kingambit"
            "|-damage|p1a: Kingambit|46/100",
            "|-enditem|p1a: Kingambit|Air Balloon",
            "|move|p1a: Kingambit|Sucker Punch||[still]",
            "|-fail|p1a: Kingambit",
            "|",
            "|upkeep",
            "|turn|7",
        ]

        process_battle_updates(self.battle)

        self.assertEqual(
            150,
            self.battle.opponent.slot_a.active.speed_range.min,
        )

    def test_sets_minspeed_when_opponent_goes_first(self):
        # opponent should have min speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150

        self.battle.msg_list = [
            "|move|p2a: Caterpie|Stealth Rock|",
            "|move|p1a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)

        self.assertEqual(
            self.battle.user.slot_a.active.stats[constants.SPEED],
            self.battle.opponent.slot_a.active.speed_range.min,
        )

    def test_sets_maxspeed_when_opponent_goes_first_in_trickroom(self):
        # opponent should have min speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.trick_room = True

        self.battle.msg_list = [
            "|move|p2a: Caterpie|Stealth Rock|",
            "|move|p1a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)

        self.assertEqual(
            self.battle.user.slot_a.active.stats[constants.SPEED],
            self.battle.opponent.slot_a.active.speed_range.max,
        )

    def test_nothing_happens_with_priority_move_in_trickroom(self):
        # opponent should have min speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.trick_room = True

        self.battle.msg_list = [
            "|move|p2a: Caterpie|Aqua Jet|",
            "|move|p1a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)

        self.assertEqual(
            float("inf"), self.battle.opponent.slot_a.active.speed_range.max
        )
        self.assertEqual(0, self.battle.opponent.slot_a.active.speed_range.min)

    def test_accounts_for_paralysis_when_calculating_speed_range(self):
        # opponent should have min speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.opponent.slot_a.active.status = constants.PARALYZED

        self.battle.msg_list = [
            "|move|p2a: Caterpie|Stealth Rock|",
            "|move|p1a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)

        # bot_speed * 2 should be the minspeed it has b/c it went first with paralysis
        expected_min_speed = int(
            self.battle.user.slot_a.active.stats[constants.SPEED] * 2
        )

        self.assertEqual(
            expected_min_speed, self.battle.opponent.slot_a.active.speed_range.min
        )

    def test_accounts_for_paralysis_on_bots_side_when_calculating_speed_range(self):
        # opponent should have min speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.user.slot_a.active.status = constants.PARALYZED

        self.battle.msg_list = [
            "|move|p2a: Caterpie|Stealth Rock|",
            "|move|p1a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)

        # bot_speed / 2 should be the minspeed it has b/c it went first with paralysis
        expected_min_speed = int(
            self.battle.user.slot_a.active.stats[constants.SPEED] / 2
        )

        self.assertEqual(
            expected_min_speed, self.battle.opponent.slot_a.active.speed_range.min
        )

    def test_accounts_for_tailwind_on_opponent_side_when_calculating_speed_ranges(self):
        # opponent should have min speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 300
        self.battle.opponent.side_conditions[constants.TAILWIND] = 1

        self.battle.msg_list = [
            "|move|p2a: Caterpie|Stealth Rock|",
            "|move|p1a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)

        # bot_speed / 2 should be the minspeed it has b/c it went first with tailwind up
        expected_min_speed = int(
            self.battle.user.slot_a.active.stats[constants.SPEED] / 2
        )

        self.assertEqual(
            expected_min_speed, self.battle.opponent.slot_a.active.speed_range.min
        )

    def test_accounts_for_tailwind_on_bot_side_when_calculating_speed_ranges(self):
        # opponent should have min speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 300
        self.battle.user.side_conditions[constants.TAILWIND] = 1

        self.battle.msg_list = [
            "|move|p2a: Caterpie|Stealth Rock|",
            "|move|p1a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)

        # bot_speed * 2 should be the minspeed it has b/c it went first with tailwind up
        expected_min_speed = int(
            self.battle.user.slot_a.active.stats[constants.SPEED] * 2
        )

        self.assertEqual(
            expected_min_speed, self.battle.opponent.slot_a.active.speed_range.min
        )

    def test_accounts_for_tailwind_on_both_side_when_calculating_speed_ranges(self):
        # opponent should have min speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 300
        self.battle.user.side_conditions[constants.TAILWIND] = 1
        self.battle.opponent.side_conditions[constants.TAILWIND] = 1

        self.battle.msg_list = [
            "|move|p2a: Caterpie|Stealth Rock|",
            "|move|p1a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)

        # bot_speed / 2 should be the minspeed it has b/c it went first with tailwind up
        expected_min_speed = int(
            self.battle.user.slot_a.active.stats[constants.SPEED] / 2
        )

        # bot_speed * 2 should be the minspeed it has b/c it went first with tailwind up
        expected_min_speed = int(expected_min_speed * 2)

        self.assertEqual(
            expected_min_speed, self.battle.opponent.slot_a.active.speed_range.min
        )

    def test_does_not_set_minspeed_when_opponent_could_have_unburden_activated(self):
        # opponent should have min speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.opponent.slot_a.active.item = None
        self.battle.opponent.slot_a.active.ability = "unburden"

        self.battle.msg_list = [
            "|move|p2a: Caterpie|Stealth Rock|",
            "|move|p1a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)

        self.assertEqual(0, self.battle.opponent.slot_a.active.speed_range.min)

    def test_sets_maxspeed_when_bot_goes_first(self):
        # opponent should have max speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150

        self.battle.msg_list = [
            "|move|p1a: Caterpie|Stealth Rock|",
            "|move|p2a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)

        self.assertEqual(
            self.battle.user.slot_a.active.stats[constants.SPEED],
            self.battle.opponent.slot_a.active.speed_range.max,
        )

    def test_minspeed_accounts_for_swiftswim(self):
        # opponent should have max speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.weather = constants.RAIN
        self.battle.opponent.slot_a.active.ability = "swiftswim"

        self.battle.msg_list = [
            "|move|p2a: Caterpie|Stealth Rock|",
            "|move|p1a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)

        self.assertEqual(150 / 2, self.battle.opponent.slot_a.active.speed_range.min)

    def test_minspeed_is_set_when_only_rain_is_up(self):
        # opponent should have max speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.weather = constants.RAIN

        self.battle.msg_list = [
            "|move|p2a: Caterpie|Stealth Rock|",
            "|move|p1a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)

        self.assertEqual(
            self.battle.user.slot_a.active.stats[constants.SPEED],
            self.battle.opponent.slot_a.active.speed_range.min,
        )

    def test_minspeed_is_set_when_rain_is_not_up_but_opponent_could_have_swiftswim(
        self,
    ):
        # opponent should have max speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.opponent.slot_a.active.name = "seismitoad"

        self.battle.msg_list = [
            "|move|p2a: Caterpie|Stealth Rock|",
            "|move|p1a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)

        self.assertEqual(
            self.battle.user.slot_a.active.stats[constants.SPEED],
            self.battle.opponent.slot_a.active.speed_range.min,
        )

    def test_minspeed_accounts_for_choicescarf(self):
        # opponent should have max speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.opponent.slot_a.active.item = "choicescarf"

        self.battle.msg_list = [
            "|move|p2a: Caterpie|Stealth Rock|",
            "|move|p1a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)

        self.assertEqual(150 / 1.5, self.battle.opponent.slot_a.active.speed_range.min)

    def test_minspeed_is_correctly_set_when_bot_has_choicescarf(self):
        # opponent should have max speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.user.slot_a.active.item = "choicescarf"

        self.battle.msg_list = [
            "|move|p1a: Caterpie|Stealth Rock|",
            "|move|p2a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)

        self.assertEqual(
            self.battle.user.slot_a.active.stats[constants.SPEED] * 1.5,
            self.battle.opponent.slot_a.active.speed_range.max,
        )

    def test_minspeed_is_correctly_set_when_bot_has_choicescarf_and_opponent_is_boosted(
        self,
    ):
        # opponent should have max speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 317
        self.battle.opponent.slot_a.active.stats[constants.SPEED] = 383
        self.battle.user.slot_a.active.item = "choicescarf"
        self.battle.opponent.slot_a.active.boosts[constants.SPEED] = 1

        self.battle.msg_list = [
            "|move|p2a: Caterpie|Stealth Rock|",
            "|move|p1a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)

        # this is meant to show the rounding inherent with way pokemon floors values
        # floor(317 / 1.5) = 211
        # floor(211*1.5) = 316
        expected_speed = int(
            self.battle.user.slot_a.active.stats[constants.SPEED] / 1.5
        )
        expected_speed = int(expected_speed * 1.5)

        self.assertEqual(
            expected_speed, self.battle.opponent.slot_a.active.speed_range.min
        )

    def test_minspeed_interaction_with_boosted_speed(self):
        # opponent should have max speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.opponent.slot_a.active.boosts[constants.SPEED] = 1

        self.battle.msg_list = [
            "|move|p2a: Caterpie|Stealth Rock|",
            "|move|p1a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)

        # the minspeed should take into account the fact that the opponent has a boost
        # therefore, the minimum (unboosted) speed must be divided by the boost multiplier
        expected_min_speed = int(
            150
            / boost_multiplier_lookup[
                self.battle.opponent.slot_a.active.boosts[constants.SPEED]
            ]
        )

        self.assertEqual(
            expected_min_speed, self.battle.opponent.slot_a.active.speed_range.min
        )

    def test_minspeed_interaction_with_bots_boosted_speed(self):
        # opponent should have max speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.user.slot_a.active.boosts[constants.SPEED] = 1

        self.battle.msg_list = [
            "|move|p2a: Caterpie|Stealth Rock|",
            "|move|p1a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)

        # the minspeed should take into account the fact that the opponent has a boost
        # therefore, the minimum (unboosted) speed must be divided by the boost multiplier
        expected_min_speed = int(
            150
            * boost_multiplier_lookup[
                self.battle.user.slot_a.active.boosts[constants.SPEED]
            ]
            / boost_multiplier_lookup[
                self.battle.opponent.slot_a.active.boosts[constants.SPEED]
            ]
        )

        self.assertEqual(
            expected_min_speed, self.battle.opponent.slot_a.active.speed_range.min
        )

    def test_minspeed_interaction_with_bot_and_opponents_boosted_speed(self):
        # opponent should have max speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.user.slot_a.active.boosts[constants.SPEED] = 1
        self.battle.opponent.slot_a.active.boosts[constants.SPEED] = 3

        self.battle.msg_list = [
            "|move|p2a: Caterpie|Stealth Rock|",
            "|move|p1a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)

        # the minspeed should take into account the fact that the opponent has a boost
        # therefore, the minimum (unboosted) speed must be divided by the boost multiplier
        expected_min_speed = int(
            150
            * boost_multiplier_lookup[
                self.battle.user.slot_a.active.boosts[constants.SPEED]
            ]
            / boost_multiplier_lookup[
                self.battle.opponent.slot_a.active.boosts[constants.SPEED]
            ]
        )

        self.assertEqual(
            expected_min_speed, self.battle.opponent.slot_a.active.speed_range.min
        )

    def test_opponents_unknown_move_is_used_as_a_zero_priority_move(self):
        # opponent should have max speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150

        self.battle.msg_list = [
            "|move|p2a: Caterpie|unknown-move|",
            "|move|p1a: Caterpie|unknown-move|",
        ]

        process_battle_updates(self.battle)

        self.assertEqual(150, self.battle.opponent.slot_a.active.speed_range.min)

    def test_bots_unknown_move_is_used_as_a_zero_priority_move(self):
        # opponent should have max speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150

        self.battle.msg_list = [
            "|move|p1a: Caterpie|unknown-move|",
            "|move|p2a: Caterpie|unknown-move|",
        ]

        process_battle_updates(self.battle)

        self.assertEqual(150, self.battle.opponent.slot_a.active.speed_range.max)

    def test_opponent_has_unknown_choicescarf_causing_it_to_be_faster(self):
        # Situation:
        #   The opponent's pokemon has a choice scarf but the bot doesn't know that - it only sees it's item as unknown
        #   The choicescarf causes the opponent to go first, when it wouldn't have gone first normally
        #   If the opponent didn't have a choicescarf it COULD still be naturally faster than the bot's pokemon
        #   This means the check_choicescarf function won't assign a choicescarf
        # Expected Result:
        #   min_speed should be set to the bot's speed. The set inferral DOES take into account items when validating
        #   the final speed

        # opponent should have max speed equal to the bot's speed
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150

        self.battle.msg_list = [
            "|move|p2a: Caterpie|Stealth Rock|",
            "|move|p1a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)
        expected_min_speed = 150
        self.assertEqual(
            expected_min_speed, self.battle.opponent.slot_a.active.speed_range.min
        )

    def test_opponent_using_grassyglide_in_grassy_terrain_does_not_cause_minspeed_to_be_set(
        self,
    ):
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.field = constants.GRASSY_TERRAIN

        self.battle.msg_list = [
            "|move|p2a: Caterpie|Grassy Glide|",
            "|move|p1a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)
        self.assertEqual(0, self.battle.opponent.slot_a.active.speed_range.min)

    def test_bot_using_grassyglide_in_grassy_terrain_does_not_cause_maxspeed_to_be_set(
        self,
    ):
        self.battle.user.slot_a.active.stats[constants.SPEED] = 150
        self.battle.field = constants.GRASSY_TERRAIN

        self.battle.msg_list = [
            "|move|p1a: Caterpie|Grassy Glide|",
            "|move|p2a: Caterpie|Stealth Rock|",
        ]

        process_battle_updates(self.battle)
        self.assertEqual(
            float("inf"), self.battle.opponent.slot_a.active.speed_range.max
        )

    def test_move_from_magicbounce_after_switching_does_not_set_speed_range(self):
        user_reserve_weedle = Pokemon("Weedle", 100)
        self.battle.user.reserve = [user_reserve_weedle]

        self.battle.msg_list = [
            "|switch|p1a: Caterpie|Caterpie, F|255/255",
            "|move|p2a: Caterpie|Stealth Rock|",
            "|move|p1a: Caterpie|Stealth Rock|p2a: Caterpie|[from]ability: Magic Bounce",
        ]

        process_battle_updates(self.battle)

        # speed ranges should be unchanged because this was a switch-in
        self.assertEqual(
            float("inf"), self.battle.opponent.slot_a.active.speed_range.max
        )
        self.assertEqual(0, self.battle.opponent.slot_a.active.speed_range.min)


class TestRemoveItem(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active
        self.battle.opponent.slot_a.active.ability = None

        self.user_active = Pokemon("weedle", 100)
        self.battle.user.slot_a.active = self.user_active

        self.username = "CoolUsername"

        self.battle.username = self.username

    def test_adds_unburden_when_appropriate(self):
        self.battle.opponent.slot_a.active.name = "hawlucha"
        self.battle.opponent.slot_a.active.item = "sitrusberry"
        split_msg = ["", "-enditem", "p2a: Hawlucha", "Sitrus Berry"]

        remove_item(self.battle, split_msg)
        self.assertIn("unburden", self.battle.opponent.slot_a.active.volatile_statuses)

    def test_basic_removes_item(self):
        self.battle.opponent.slot_a.active.item = "airballoon"
        split_msg = ["", "-enditem", "p2a: Caterpie", "Air Balloon"]

        remove_item(self.battle, split_msg)
        self.assertEqual(None, self.battle.opponent.slot_a.active.item)

    def test_sets_removed_item_when_item_ends(self):
        self.battle.opponent.slot_a.active.item = "airballoon"
        split_msg = ["", "-enditem", "p2a: Caterpie", "Air Balloon"]

        remove_item(self.battle, split_msg)
        self.assertEqual("airballoon", self.battle.opponent.slot_a.active.removed_item)


class TestInactive(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active
        self.battle.opponent.slot_a.active.ability = None

        self.user_active = Pokemon("weedle", 100)
        self.battle.user.slot_a.active = self.user_active

        self.username = "CoolUsername"

        self.battle.username = self.username

    def test_sets_time_to_15_seconds(self):
        split_msg = ["", "inactive", "Time left: 135 sec this turn", "135 sec total"]
        inactive(self.battle, split_msg)

        self.assertEqual(135, self.battle.time_remaining)

    def test_sets_to_60_seconds(self):
        split_msg = ["", "inactive", "Time left: 60 sec this turn", "60 sec total"]
        inactive(self.battle, split_msg)

        self.assertEqual(60, self.battle.time_remaining)

    def test_capture_group_failing(self):
        self.battle.time_remaining = 1
        split_msg = ["", "inactive", "some random message"]
        inactive(self.battle, split_msg)

        self.assertEqual(1, self.battle.time_remaining)

    def test_capture_group_failing_but_message_starts_with_username(self):
        self.battle.time_remaining = 1
        split_msg = ["", "inactive", "Time left: some random message"]
        inactive(self.battle, split_msg)

        self.assertEqual(1, self.battle.time_remaining)

    def test_different_inactive_message_does_not_change_time(self):
        self.battle.time_remaining = 1
        split_msg = ["", "inactive", "Some Other Person has 10 seconds left"]
        inactive(self.battle, split_msg)

        self.assertEqual(1, self.battle.time_remaining)


class TestInactiveOff(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active
        self.battle.opponent.slot_a.active.ability = None
        self.battle.opponent.slot_b.active = Pokemon("weedle", 100)

        self.user_active = Pokemon("caterpie", 100)
        self.battle.user.slot_a.active = self.user_active
        self.battle.user.slot_a.active.previous_hp = self.battle.user.slot_a.active.hp
        self.battle.user.slot_b.active = Pokemon("weedle", 100)

        self.username = "CoolUsername"

        self.battle.username = self.username

        self.battle.user.last_used_move = LastUsedMove("caterpie", "tackle", 0)

        self.battle.request_json = {
            constants.ACTIVE: [{constants.MOVES: []}],
            constants.SIDE: {
                constants.ID: None,
                constants.NAME: None,
                constants.POKEMON: [],
                constants.RQID: None,
            },
        }

    def test_turns_timer_off(self):
        self.battle.time_remaining = 60
        self.battle.msg_list = [
            "|move|p2a: Caterpie|Tackle|",
            "|-damage|p1a: Caterpie|186/252",
            "|move|p1a: Caterpie|Tackle|",
            "|-damage|p2a: Caterpie|85/100",
            "|upkeep",
            "|inactiveoff|Battle timer is now OFF.",  # this line is being tested
            "|turn|4",
        ]
        process_battle_updates(self.battle)
        self.assertIsNone(self.battle.time_remaining)


class TestNoInit(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)

        self.battle.user.name = "p1"
        self.battle.user.slot_a.active = Pokemon("Caterpie", 100)

        self.battle.opponent.name = "p2"
        self.battle.opponent.slot_a.active = Pokemon("Pikachu", 100)

    def test_renames_battle_when_rename_message_occurs(self):
        self.battle.battle_tag = "original_tag"
        new_battle_tag = "new_battle_tag"

        self.battle.msg_list = ["|noinit|rename|{}".format(new_battle_tag)]

        process_battle_updates(self.battle)

        self.assertEqual(self.battle.battle_tag, new_battle_tag)


class TestSetsStellarBoost(unittest.TestCase):
    def setUp(self):
        self.battle = Battle(None)
        self.battle.user.name = "p1"
        self.battle.opponent.name = "p2"

        self.opponent_active = Pokemon("caterpie", 100)
        self.battle.opponent.slot_a.active = self.opponent_active
        self.battle.opponent.slot_b.active = Pokemon("torkoal", 100)

        self.user_active = Pokemon("weedle", 100)
        self.battle.user.slot_a.active = self.user_active
        self.battle.user.slot_b.active = Pokemon("charmander", 100)

    def test_sets_stellar_boost_if_damage_dealt_by_terastallized_stellar_pkmn(self):
        self.battle.opponent.slot_a.active.hp = 100
        self.battle.opponent.slot_a.active.max_hp = 100
        self.battle.user.slot_b.active.tera_type = "stellar"
        self.battle.user.slot_b.active.terastallized = True
        self.battle.msg_list = [
            "|move|p1b: Charmander|Tackle|p2a: Caterpie",
            "|-damage|p2a: Caterpie|75/100",
        ]

        process_battle_updates(self.battle)
        self.assertIn("normal", self.battle.user.slot_b.active.stellar_boosted_types)

    def test_sets_stellar_boost_for_opponent_if_damage_dealt_by_terastallized_stellar_pkmn(
        self,
    ):
        self.battle.user.slot_a.active.hp = 100
        self.battle.user.slot_a.active.max_hp = 100
        self.battle.opponent.slot_b.active.tera_type = "stellar"
        self.battle.opponent.slot_b.active.terastallized = True
        self.battle.msg_list = [
            "|move|p2b: Caterpie|Tackle|p1a: Charmander",
            "|-damage|p1a: Charmander|75/100",
        ]

        process_battle_updates(self.battle)
        self.assertIn(
            "normal", self.battle.opponent.slot_b.active.stellar_boosted_types
        )

    def test_does_not_set_stellar_type_boost_if_terapagos_stellar(self):
        self.battle.opponent.slot_a.active.hp = 100
        self.battle.opponent.slot_a.active.max_hp = 100
        self.battle.user.slot_b.active.name = "terapagosstellar"
        self.battle.user.slot_b.active.tera_type = "stellar"
        self.battle.user.slot_b.active.terastallized = True
        self.battle.msg_list = [
            "|move|p1b: Terapagos-Stellar|Tackle|p2a: Caterpie",
            "|-damage|p2a: Caterpie|75/100",
        ]

        process_battle_updates(self.battle)
        self.assertNotIn("normal", self.battle.user.slot_b.active.stellar_boosted_types)
