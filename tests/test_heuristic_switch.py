import unittest

from fp.battle import Battle, Pokemon, Slot
from fp.heuristic import _best_switch, pick_moves, _on_field_species


class TestHeuristicSwitch(unittest.TestCase):
    def _bench_mon(self, name, index, hp=100, max_hp=100):
        p = Pokemon(name, max_hp)
        p.index = index
        p.hp = hp
        p.max_hp = max_hp
        p.add_move("protect")
        return p

    def setUp(self):
        self.battle = Battle("gen9")
        self.battle.user.name = "p1"
        self.battle.user.slot_a = Slot("a")
        self.battle.user.slot_b = Slot("b")
        self.battle.user.slot_a.active = Pokemon("farigiraf", 100)
        self.battle.user.slot_a.active.hp = 0
        self.battle.user.slot_b.active = Pokemon("pelipper", 100)
        self.battle.user.slot_b.active.hp = 80
        self.battle.user.slot_b.active.max_hp = 100
        self.battle.user.reserve = [
            self._bench_mon("blastoise", 3),
            self._bench_mon("incineroar", 4),
            self._bench_mon("pelipper", 5),
        ]
        self.battle.opponent.slot_a = Slot("a")
        self.battle.opponent.slot_b = Slot("b")
        self.battle.opponent.slot_a.active = Pokemon("kingambit", 100)
        self.battle.opponent.slot_b.active = Pokemon("archaludon", 100)
        self.battle.force_switch = (True, False)
        self.battle.trick_room = False
        self.battle.weather = None
        self.battle.turn = 3

    def test_best_switch_excludes_on_field_partner(self):
        chosen = _best_switch(self.battle, 0, set())
        self.assertIsNotNone(chosen)
        self.assertNotEqual(chosen.name, "pelipper")

    def test_double_force_switch_picks_two_different_mons(self):
        self.battle.user.slot_b.active = Pokemon("pelipper", 100)
        self.battle.user.slot_b.active.hp = 0
        self.battle.force_switch = (True, True)
        a, b = pick_moves(self.battle)
        self.assertTrue(a.startswith("switch "))
        self.assertTrue(b.startswith("switch "))
        name_a = a.split("switch ", 1)[1]
        name_b = b.split("switch ", 1)[1]
        self.assertNotEqual(name_a, name_b)

    def test_double_force_switch_one_reserve_passes_second_slot(self):
        """With only one living reserve, second force-switch slot must pass."""
        self.battle.user.slot_b.active = Pokemon("pelipper", 100)
        self.battle.user.slot_b.active.hp = 0
        self.battle.user.slot_b.active.fainted = True
        self.battle.force_switch = (True, True)
        self.battle.user.reserve = [self._bench_mon("garchomp", 3)]
        a, b = pick_moves(self.battle)
        switches = [c for c in (a, b) if c.startswith("switch ")]
        passes = [c for c in (a, b) if c == "no move"]
        self.assertEqual(len(switches), 1)
        self.assertEqual(len(passes), 1)
        self.assertEqual(switches[0], "switch garchomp")

    def test_force_switch_no_reserves_both_pass(self):
        self.battle.user.slot_b.active = Pokemon("pelipper", 100)
        self.battle.user.slot_b.active.hp = 0
        self.battle.user.slot_b.active.fainted = True
        self.battle.force_switch = (True, True)
        self.battle.user.reserve = []
        a, b = pick_moves(self.battle)
        self.assertEqual(a, "no move")
        self.assertEqual(b, "no move")

    def test_on_field_species_includes_only_living_actives(self):
        keys = _on_field_species(self.battle.user)
        self.assertNotIn("farigiraf", keys)  # fainted
        self.assertIn("pelipper", keys)


if __name__ == "__main__":
    unittest.main()
