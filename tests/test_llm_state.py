import unittest

import constants
from fp.battle import Battle, Pokemon, Slot
from fp.llm_state import (
    build_active_speed_order,
    build_decision_state,
    build_type_effectiveness_matrix,
    legal_actions_for_slot,
    validate_move_choices,
    validate_team_preview_digits,
)


class TestLlmState(unittest.TestCase):
    def setUp(self):
        self.battle = Battle("gen9")
        self.battle.turn = 2
        self.battle.user.name = "p1"
        self.battle.user.slot_a = Slot("a")
        self.battle.user.slot_b = Slot("b")
        self.battle.user.slot_a.active = Pokemon("charizard", 100)
        self.battle.user.slot_a.active.hp = 80
        self.battle.user.slot_a.active.max_hp = 100
        self.battle.user.slot_a.active.add_move("heatwave")
        self.battle.user.slot_a.active.add_move("protect")
        self.battle.user.slot_b.active = Pokemon("aerodactyl", 100)
        self.battle.user.slot_b.active.hp = 90
        self.battle.user.slot_b.active.max_hp = 100
        self.battle.user.slot_b.active.add_move("rockslide")
        self.battle.user.slot_b.active.add_move("tailwind")
        bench = Pokemon("garchomp", 100)
        bench.index = 3
        bench.hp = 100
        bench.max_hp = 100
        bench.add_move("earthquake")
        self.battle.user.reserve = [bench]
        self.battle.opponent.slot_a = Slot("a")
        self.battle.opponent.slot_b = Slot("b")
        self.battle.opponent.slot_a.active = Pokemon("incineroar", 100)
        self.battle.opponent.slot_b.active = Pokemon("rillaboom", 100)
        self.battle.force_switch = (False, False)

    def test_legal_actions_include_moves_and_switch(self):
        legal_a = legal_actions_for_slot(self.battle, 0)
        self.assertIn("heatwave", legal_a)
        self.assertIn("protect", legal_a)
        self.assertIn("switch garchomp", legal_a)

    def test_build_decision_state_has_whitelists(self):
        state = build_decision_state(self.battle)
        self.assertIn("legal_actions", state["slot_a"])
        self.assertTrue(state["slot_a"]["legal_actions"])
        self.assertEqual(state["turn"], 2)
        self.assertIn("active_speed_order", state)
        self.assertIn("type_effectiveness_matrix", state)
        self.assertTrue(state["meta_hints"])

    def test_active_speed_order_respects_tailwind(self):
        self.battle.user.side_conditions[constants.TAILWIND] = 3
        order = build_active_speed_order(self.battle)
        names = [e["name"] for e in order]
        self.assertEqual(len(order), 4)
        self.assertIn("aerodactyl", names)
        aero = next(e for e in order if e["name"] == "aerodactyl")
        self.assertIn("Tailwind", aero["notes"])
        # With Tailwind, user Aerodactyl should outspeed non-boosted foes.
        self.assertEqual(order[0]["side"], "user")

    def test_type_matrix_marks_ability_immunity(self):
        self.battle.user.slot_a.active = Pokemon("garchomp", 100)
        self.battle.user.slot_a.active.add_move("earthquake")
        self.battle.opponent.slot_a.active = Pokemon("gengar", 100)
        self.battle.opponent.slot_a.active.ability = "levitate"
        matrix = build_type_effectiveness_matrix(self.battle)
        eq = matrix["garchomp"]["earthquake"]["opponent_slot_a"]
        self.assertEqual(eq["multiplier"], 0.0)
        self.assertIn("levitate", eq["label"])

    def test_type_matrix_super_effective(self):
        self.battle.user.slot_a.active = Pokemon("charizard", 100)
        self.battle.user.slot_a.active.add_move("heatwave")
        self.battle.opponent.slot_b.active = Pokemon("ferrothorn", 100)
        matrix = build_type_effectiveness_matrix(self.battle)
        hw = matrix["charizard"]["heatwave"]["opponent_slot_b"]
        self.assertGreaterEqual(hw["multiplier"], 2.0)

    def test_validate_rejects_illegal_and_duplicate_switch(self):
        ok, _ = validate_move_choices(
            "heatwave", "rockslide", ["heatwave"], ["rockslide"]
        )
        self.assertTrue(ok)
        ok, reason = validate_move_choices(
            "fakeout", "rockslide", ["heatwave"], ["rockslide"]
        )
        self.assertFalse(ok)
        ok, reason = validate_move_choices(
            "switch garchomp",
            "switch garchomp",
            ["switch garchomp"],
            ["switch garchomp"],
        )
        self.assertFalse(ok)
        self.assertIn("same pokemon", reason)

    def test_validate_team_preview_digits(self):
        ok, _ = validate_team_preview_digits("1234", ["1", "2", "3", "4", "5", "6"])
        self.assertTrue(ok)
        ok, _ = validate_team_preview_digits("1123", ["1", "2", "3", "4"])
        self.assertFalse(ok)
        ok, _ = validate_team_preview_digits("123", ["1", "2", "3", "4"])
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
