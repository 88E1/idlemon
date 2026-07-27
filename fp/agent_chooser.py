"""
File-handoff chooser for decisions made in the Cursor chat agent (e.g. Gemini 3.5 Flash).

Protocol:
  1. Bot writes llm_exchange/pending.json with battle state + legal actions.
  2. Cursor agent reads it, writes llm_exchange/decision.json with the same id.
  3. Bot validates, applies the choice, and clears the exchange files.

Fallback: heuristic if timeout / invalid / missing decision.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path

from config import FoulPlayConfig
from fp.heuristic import pick_moves, pick_team_preview_digits
from fp.llm_state import (
    build_decision_state,
    build_team_preview_state,
    validate_move_choices,
    validate_team_preview_digits,
)

logger = logging.getLogger(__name__)

EXCHANGE_DIR = Path(__file__).resolve().parent.parent / "llm_exchange"
PENDING_PATH = EXCHANGE_DIR / "pending.json"
DECISION_PATH = EXCHANGE_DIR / "decision.json"
POLL_INTERVAL_S = 0.25


def _ensure_dir():
    EXCHANGE_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write(path: Path, payload: dict):
    _ensure_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _clear_exchange():
    for p in (PENDING_PATH, DECISION_PATH):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def _read_decision(expected_id: str) -> dict | None:
    if not DECISION_PATH.exists():
        return None
    try:
        data = json.loads(DECISION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("id") != expected_id:
        return None
    return data


def _wait_for_decision(request_id: str, kind: str) -> dict:
    timeout_ms = FoulPlayConfig.llm_timeout_ms
    deadline = time.monotonic() + max(1.0, timeout_ms / 1000.0)
    logger.info(
        "Waiting for Cursor agent decision (%s) id=%s timeout=%sms path=%s",
        kind,
        request_id,
        timeout_ms,
        DECISION_PATH,
    )
    while time.monotonic() < deadline:
        data = _read_decision(request_id)
        if data is not None:
            return data
        time.sleep(POLL_INTERVAL_S)
    raise TimeoutError(
        f"No agent decision for {kind} id={request_id} within {timeout_ms}ms. "
        f"Write {DECISION_PATH} while logged into Cursor as Gemini 3.5 Flash."
    )


def pick_moves_agent(battle) -> tuple[str, str]:
    # Faint replacements must be answered immediately with switch/pass.
    # Do not wait on the Cursor chat agent for these.
    if any(battle.force_switch):
        choice_a, choice_b = pick_moves(battle)
        logger.info(
            "Force-switch auto-resolved (heuristic): %s | %s", choice_a, choice_b
        )
        return choice_a, choice_b

    state = build_decision_state(battle)
    legal_a = state["slot_a"]["legal_actions"]
    legal_b = state["slot_b"]["legal_actions"]
    request_id = uuid.uuid4().hex[:12]

    _clear_exchange()
    _atomic_write(
        PENDING_PATH,
        {
            "id": request_id,
            "kind": "move",
            "turn": battle.turn,
            "battle_tag": getattr(battle, "battle_tag", None),
            "state": state,
            "response_schema": {
                "id": request_id,
                "slot_a": "<one of state.slot_a.legal_actions>",
                "slot_b": "<one of state.slot_b.legal_actions>",
                "reason": "<short>",
            },
            "instruction": (
                "You are the Cursor chat agent (use Gemini 3.5 Flash). "
                "Pick legal actions for both doubles slots. "
                "Use state.active_speed_order for turn order (Trick Room reverses it). "
                "ALWAYS check state.priority_threats first (Ice Shard/Sucker Punch/Fake Out "
                "move before speed). "
                "Use state.incoming_ko_matrix — if a foe can KO you (esp. priority), Protect. "
                "Use state.damage_ko_matrix (prefer guaranteed/likely KOs). "
                "Respect state.protect_status (no consecutive Protect when risky). "
                "Use state.type_effectiveness_matrix to avoid immune (0.0) targets. "
                "Follow state.opponent_inferences, state.turn_plan_hints, "
                "state.meta_hints, and state.team_roles. "
                f"Write llm_exchange/decision.json with the same id ({request_id}). "
                "Do not invent moves outside legal_actions."
            ),
        },
    )
    logger.info(
        "Agent move request ready turn=%s id=%s -> %s",
        battle.turn,
        request_id,
        PENDING_PATH,
    )

    try:
        data = _wait_for_decision(request_id, "move")
        slot_a = str(data.get("slot_a", "")).strip()
        slot_b = str(data.get("slot_b", "")).strip()
        ok, reason = validate_move_choices(slot_a, slot_b, legal_a, legal_b)
        if not ok:
            raise ValueError(reason)
        logger.info(
            "Agent chose turn %s: %s | %s (%s)",
            battle.turn,
            slot_a,
            slot_b,
            data.get("reason", ""),
        )
        return slot_a, slot_b
    except Exception as e:
        logger.warning("Agent move selection failed (%s); using heuristic fallback", e)
        choice_a, choice_b = pick_moves(battle)
        logger.info(
            "Heuristic fallback turn %s: %s | %s", battle.turn, choice_a, choice_b
        )
        return choice_a, choice_b
    finally:
        _clear_exchange()


def pick_team_preview_digits_agent(battle) -> str:
    state = build_team_preview_state(battle)
    legal = state["legal_indices"]
    request_id = uuid.uuid4().hex[:12]

    _clear_exchange()
    _atomic_write(
        PENDING_PATH,
        {
            "id": request_id,
            "kind": "team_preview",
            "battle_tag": getattr(battle, "battle_tag", None),
            "state": state,
            "response_schema": {
                "id": request_id,
                "digits": "ABCD",
                "reason": "<short>",
            },
            "instruction": (
                "You are the Cursor chat agent (use Gemini 3.5 Flash). "
                "Pick 4 distinct party indices: lead_a, lead_b, reserve_1, reserve_2. "
                "Prefer state.recommended_preview.digits unless you have a clear better plan. "
                "Use state.opponent_inferences and state.team_roles. "
                f"Write llm_exchange/decision.json with the same id ({request_id})."
            ),
        },
    )
    logger.info("Agent team-preview request ready id=%s -> %s", request_id, PENDING_PATH)

    try:
        data = _wait_for_decision(request_id, "team_preview")
        digits = str(data.get("digits", "")).strip()
        ok, reason = validate_team_preview_digits(digits, legal)
        if not ok:
            raise ValueError(reason)
        logger.info(
            "Agent team-preview digits=%s (%s)", digits, data.get("reason", "")
        )
        return digits
    except Exception as e:
        logger.warning(
            "Agent team-preview failed (%s); using heuristic fallback", e
        )
        digits = pick_team_preview_digits(battle)
        logger.info("Heuristic team-preview fallback: %s", digits)
        return digits
    finally:
        _clear_exchange()
