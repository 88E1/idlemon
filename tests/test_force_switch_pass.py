import unittest

from fp.battle import Battle, Pokemon, Slot
from fp.helpers import is_replacement_request
from fp.heuristic import pick_moves
from fp.llm_state import legal_actions_for_slot
from fp.search.helpers import format_decision


class TestForceSwitchPass(unittest.TestCase):
    def setUp(self):
        self.battle = Battle("gen9")
        self.battle.turn = 4
        self.battle.user.name = "p1"
        self.battle.user.slot_a = Slot("a")
        self.battle.user.slot_b = Slot("b")
        self.battle.user.slot_a.active = Pokemon("kingambit", 100)
        self.battle.user.slot_a.active.hp = 0
        self.battle.user.slot_a.active.fainted = True
        self.battle.user.slot_a.active.index = 1
        self.battle.user.slot_b.active = Pokemon("charizard", 100)
        self.battle.user.slot_b.active.hp = 80
        self.battle.user.slot_b.active.max_hp = 100
        self.battle.user.slot_b.active.index = 2
        self.battle.user.slot_b.active.add_move("heatwave")
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
        # Pure replacement request: forceSwitch, no active moves list
        self.battle.force_switch = (True, False)
        self.battle.request_json = {"forceSwitch": [True, False], "rqid": 9}

    def test_is_replacement_request(self):
        self.assertTrue(is_replacement_request(self.battle))
        self.battle.request_json["active"] = [{"moves": []}]
        self.assertFalse(is_replacement_request(self.battle))

    def test_living_slot_must_pass_on_replacement(self):
        self.assertEqual(legal_actions_for_slot(self.battle, 1), ["no move"])
        legal_a = legal_actions_for_slot(self.battle, 0)
        self.assertTrue(any(a.startswith("switch ") for a in legal_a))

    def test_pick_moves_switch_and_pass(self):
        a, b = pick_moves(self.battle)
        self.assertTrue(a.startswith("switch "))
        self.assertEqual(b, "no move")
        self.assertEqual(format_decision(self.battle, self.battle.user.slot_b, b), "pass")
        self.assertEqual(
            format_decision(self.battle, self.battle.user.slot_a, a), "switch 3"
        )

    def test_legal_actions_no_duplicate_switch_when_one_reserve(self):
        self.battle.user.slot_b.active.hp = 0
        self.battle.user.slot_b.active.fainted = True
        self.battle.force_switch = (True, True)
        self.battle.request_json = {"forceSwitch": [True, True], "rqid": 10}
        legal_a = legal_actions_for_slot(self.battle, 0)
        already = set()
        for action in legal_a:
            if action.startswith("switch "):
                already.add(action.split("switch ", 1)[1].replace(" ", "").lower())
        legal_b = legal_actions_for_slot(self.battle, 1, already)
        self.assertTrue(any(a.startswith("switch ") for a in legal_a))
        self.assertEqual(legal_b, ["no move"])


if __name__ == "__main__":
    unittest.main()
