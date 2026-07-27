import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fp import agent_chooser
from fp.battle import Battle, Pokemon, Slot
from fp.llm_state import build_decision_state


class TestAgentChooser(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.exchange = Path(self._tmpdir.name)
        self.pending = self.exchange / "pending.json"
        self.decision = self.exchange / "decision.json"

        self.battle = Battle("gen9")
        self.battle.turn = 1
        self.battle.user.slot_a = Slot("a")
        self.battle.user.slot_b = Slot("b")
        self.battle.user.slot_a.active = Pokemon("charizard", 100)
        self.battle.user.slot_a.active.add_move("heatwave")
        self.battle.user.slot_b.active = Pokemon("aerodactyl", 100)
        self.battle.user.slot_b.active.add_move("rockslide")
        self.battle.user.reserve = []
        self.battle.opponent.slot_a = Slot("a")
        self.battle.opponent.slot_b = Slot("b")
        self.battle.opponent.slot_a.active = Pokemon("incineroar", 100)
        self.battle.opponent.slot_b.active = Pokemon("rillaboom", 100)
        self.battle.force_switch = (False, False)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_agent_picks_from_decision_file(self):
        state = build_decision_state(self.battle)
        legal_a = state["slot_a"]["legal_actions"]
        legal_b = state["slot_b"]["legal_actions"]

        def fake_wait(request_id, kind):
            return {
                "id": request_id,
                "slot_a": legal_a[0],
                "slot_b": legal_b[0],
                "reason": "test",
            }

        with (
            mock.patch.object(agent_chooser, "EXCHANGE_DIR", self.exchange),
            mock.patch.object(agent_chooser, "PENDING_PATH", self.pending),
            mock.patch.object(agent_chooser, "DECISION_PATH", self.decision),
            mock.patch.object(agent_chooser, "_wait_for_decision", side_effect=fake_wait),
            mock.patch("fp.agent_chooser.FoulPlayConfig") as cfg,
        ):
            cfg.llm_timeout_ms = 5000
            a, b = agent_chooser.pick_moves_agent(self.battle)

        self.assertEqual(a, legal_a[0])
        self.assertEqual(b, legal_b[0])
        self.assertFalse(self.pending.exists())
        self.assertFalse(self.decision.exists())

    def test_pending_written_then_cleared_on_timeout_fallback(self):
        with (
            mock.patch.object(agent_chooser, "EXCHANGE_DIR", self.exchange),
            mock.patch.object(agent_chooser, "PENDING_PATH", self.pending),
            mock.patch.object(agent_chooser, "DECISION_PATH", self.decision),
            mock.patch.object(
                agent_chooser,
                "_wait_for_decision",
                side_effect=TimeoutError("timeout"),
            ),
            mock.patch("fp.agent_chooser.FoulPlayConfig") as cfg,
            mock.patch(
                "fp.agent_chooser.pick_moves", return_value=("heatwave", "rockslide")
            ),
        ):
            cfg.llm_timeout_ms = 100
            a, b = agent_chooser.pick_moves_agent(self.battle)

        self.assertEqual((a, b), ("heatwave", "rockslide"))
        self.assertFalse(self.pending.exists())


if __name__ == "__main__":
    unittest.main()
