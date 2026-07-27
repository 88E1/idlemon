import unittest

import constants
from fp.battle import Battle, Pokemon, Slot
from fp.llm_state import build_decision_state, build_team_preview_state
from fp.vgc_intel import (
    build_damage_ko_matrix,
    build_incoming_ko_matrix,
    build_opponent_inferences,
    build_priority_threats,
    build_protect_status,
    estimate_damage,
    infer_opponent_pokemon,
    recommend_team_preview,
)


class TestVgcIntel(unittest.TestCase):
    def setUp(self):
        self.battle = Battle("gen9")
        self.battle.turn = 1
        self.battle.weather = constants.SUN
        self.battle.user.name = "p1"
        self.battle.user.slot_a = Slot("a")
        self.battle.user.slot_b = Slot("b")
        zard = Pokemon("charizard", 50)
        zard.hp = zard.max_hp
        zard.item = "charizarditey"
        zard.ability = "drought"
        zard.add_move("heatwave")
        zard.add_move("weatherball")
        zard.add_move("protect")
        self.battle.user.slot_a.active = zard
        chomp = Pokemon("garchomp", 50)
        chomp.hp = chomp.max_hp
        chomp.item = "lifeorb"
        chomp.add_move("earthquake")
        chomp.add_move("rockslide")
        self.battle.user.slot_b.active = chomp
        self.battle.user.reserve = []
        for i, name in enumerate(("whimsicott", "kingambit", "basculegion", "floetteeternal"), start=3):
            p = Pokemon(name, 50)
            p.index = i
            p.hp = p.max_hp
            self.battle.user.reserve.append(p)
        # Assign indices to actives like Showdown does
        self.battle.user.slot_a.active.index = 1
        self.battle.user.slot_b.active.index = 2

        self.battle.opponent.slot_a = Slot("a")
        self.battle.opponent.slot_b = Slot("b")
        ferro = Pokemon("ferrothorn", 50)
        ferro.hp = ferro.max_hp
        self.battle.opponent.slot_a.active = ferro
        rilla = Pokemon("rillaboom", 50)
        rilla.hp = rilla.max_hp
        self.battle.opponent.slot_b.active = rilla
        self.battle.opponent.reserve = [
            Pokemon("incineroar", 50),
            Pokemon("farigiraf", 50),
        ]
        for p in self.battle.opponent.reserve:
            p.hp = p.max_hp

    def test_estimate_damage_super_effective_fire(self):
        est = estimate_damage(
            self.battle.user.slot_a.active,
            self.battle.opponent.slot_a.active,
            "heatwave",
            self.battle,
        )
        self.assertIsNotNone(est)
        self.assertGreaterEqual(est["mult"], 2.0)
        self.assertGreater(est["dmg_pct_max"], 30)
        self.assertIn(est["ko_chance"], ("guaranteed", "likely", "chip", "low"))

    def test_estimate_damage_marks_levitate_immune(self):
        gengar = Pokemon("gengar", 50)
        gengar.ability = "levitate"
        gengar.hp = gengar.max_hp
        est = estimate_damage(
            self.battle.user.slot_b.active, gengar, "earthquake", self.battle
        )
        self.assertEqual(est["ko_chance"], "immune")
        self.assertEqual(est["dmg_pct_max"], 0.0)

    def test_damage_ko_matrix_present(self):
        matrix = build_damage_ko_matrix(self.battle)
        self.assertIn("charizard", matrix)
        self.assertIn("heatwave", matrix["charizard"])
        hw = matrix["charizard"]["heatwave"]["opponent_slot_a"]
        self.assertIn("dmg_pct", hw)
        self.assertIn("ko_chance", hw)

    def test_opponent_inferences_tags_fakeout_and_tr(self):
        info = build_opponent_inferences(self.battle)
        self.assertIn("fake_out", info["tags"])
        self.assertIn("trick_room", info["tags"])
        self.assertTrue(any(a["name"] == "rillaboom" for a in info["active"]))

    def test_recommend_team_preview_tr(self):
        # Clear actives on user so preview uses reserve indices only-ish;
        # recommend_team_preview looks at all user mons.
        rec = recommend_team_preview(self.battle)
        self.assertEqual(len(rec["digits"]), 4)
        self.assertIn("trick_room", rec["opponent_tags"])
        self.assertTrue(rec["reason"])

    def test_decision_state_includes_new_fields(self):
        self.battle.force_switch = (False, False)
        state = build_decision_state(self.battle)
        self.assertIn("damage_ko_matrix", state)
        self.assertIn("incoming_ko_matrix", state)
        self.assertIn("priority_threats", state)
        self.assertIn("protect_status", state)
        self.assertIn("opponent_inferences", state)
        self.assertIn("team_roles", state)
        self.assertIn("turn_plan_hints", state)
        self.assertTrue(state["meta_hints"])
        self.assertIn("charizard", state["team_roles"])

    def test_vanilluxe_inference_includes_iceshard(self):
        van = Pokemon("vanilluxe", 50)
        van.hp = van.max_hp
        van.add_move("blizzard")
        info = infer_opponent_pokemon(van)
        self.assertIn("iceshard", info["likely_moves"])
        self.assertIn("Ice Shard", info["threat"])

    def test_priority_threats_iceshard_vs_garchomp(self):
        # Replace foes with Vanilluxe threatening Garchomp
        van = Pokemon("vanilluxe", 50)
        van.hp = van.max_hp
        van.add_move("iceshard")
        van.add_move("blizzard")
        self.battle.opponent.slot_a.active = van
        self.battle.opponent.slot_b.active = None
        # Low HP Garchomp so Ice Shard is a real KO threat
        chomp = self.battle.user.slot_b.active
        chomp.hp = max(1, int(chomp.max_hp * 0.25))
        threats = build_priority_threats(self.battle)
        self.assertTrue(threats)
        ice = next((t for t in threats if t["move"] == "iceshard"), None)
        self.assertIsNotNone(ice)
        self.assertGreaterEqual(ice["priority"], 1)
        self.assertEqual(ice["target"], "garchomp")
        self.assertIn(ice["ko_chance"], ("guaranteed", "likely", "chip", "low"))

    def test_incoming_ko_matrix_has_priority_field(self):
        van = Pokemon("vanilluxe", 50)
        van.hp = van.max_hp
        van.add_move("iceshard")
        self.battle.opponent.slot_a.active = van
        self.battle.opponent.slot_b.active = None
        matrix = build_incoming_ko_matrix(self.battle)
        self.assertIn("vanilluxe", matrix)
        self.assertIn("iceshard", matrix["vanilluxe"])
        vs_b = matrix["vanilluxe"]["iceshard"]["slot_b"]
        self.assertEqual(vs_b.get("priority"), 1)
        self.assertIn("dmg_pct", vs_b)

    def test_protect_status_marks_consecutive_risky(self):
        zard = self.battle.user.slot_a.active
        zard.volatile_status_durations[constants.PROTECT] = 2
        status = build_protect_status(self.battle)
        self.assertTrue(status["slot_a"]["consecutive_protect_risky"])
        self.assertFalse(status["slot_b"]["consecutive_protect_risky"])

    def test_team_preview_state_has_recommendation(self):
        # Move all to reserve for preview-style party
        self.battle.user.slot_a.active = None
        self.battle.user.slot_b.active = None
        party = []
        for i, name in enumerate(
            (
                "floetteeternal",
                "charizard",
                "kingambit",
                "whimsicott",
                "basculegion",
                "garchomp",
            ),
            start=1,
        ):
            p = Pokemon(name, 50)
            p.index = i
            p.hp = p.max_hp
            party.append(p)
        self.battle.user.reserve = party
        self.battle.opponent.slot_a.active = None
        self.battle.opponent.slot_b.active = None
        state = build_team_preview_state(self.battle)
        self.assertIn("recommended_preview", state)
        self.assertEqual(len(state["recommended_preview"]["digits"]), 4)
        self.assertIn("team_roles", state)


if __name__ == "__main__":
    unittest.main()
