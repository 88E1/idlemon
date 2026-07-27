"""Cursor SDK-backed move / team-preview chooser with heuristic fallback."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
from typing import Optional

from config import FoulPlayConfig
from fp.heuristic import pick_moves, pick_team_preview_digits
from fp.llm_state import (
    build_decision_state,
    build_team_preview_state,
    validate_move_choices,
    validate_team_preview_digits,
)

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


MOVE_SYSTEM = """You are a competitive Pokemon VGC / Champions doubles decision engine.
You will receive a JSON battle state. Each slot lists legal_actions — you MUST pick
exactly one action from slot_a's legal_actions and one from slot_b's legal_actions.
Use active_speed_order for turn order (Trick Room reverses it).
ALWAYS check priority_threats first — Ice Shard / Sucker Punch / Fake Out move before speed.
Use incoming_ko_matrix: if a foe can KO you (especially with priority), Protect or don't attack into it.
Use damage_ko_matrix: prefer guaranteed/likely KOs; avoid immune targets.
Use type_effectiveness_matrix as a secondary check (0.0 = immune; prefer >= 2.0).
Respect protect_status — do not spam consecutive Protect when marked risky.
Follow opponent_inferences.threat and meta_hints / turn_plan_hints.
Respect team_roles — do not freestyle a mon away from its job.
Do not invent moves. Do not use tools. Do not edit files. Do not explain outside JSON.
Mega evolution is applied automatically when available — do not encode mega in the action.
Reply with ONLY a single JSON object:
{"slot_a":"<action>","slot_b":"<action>","reason":"<short>"}
"""

PREVIEW_SYSTEM = """You are a competitive Pokemon VGC / Champions doubles team-preview engine.
Pick exactly 4 distinct party indices. Order: lead_a, lead_b, reserve_1, reserve_2.
Prefer recommended_preview.digits unless you have a clear better plan.
Use opponent_inferences and team_roles.
Do not use tools. Do not edit files. Reply with ONLY JSON:
{"digits":"ABCD","reason":"<short>"}
where each character is a party index from legal_indices.
"""


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    text = text.strip()
    m = _JSON_FENCE_RE.search(text)
    if m:
        text = m.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _call_cursor_agent(prompt: str) -> str:
    from cursor_sdk import Agent, AgentOptions, LocalAgentOptions

    api_key = FoulPlayConfig.cursor_api_key or os.environ.get("CURSOR_API_KEY")
    model = FoulPlayConfig.llm_model
    options = AgentOptions(
        api_key=api_key,
        model=model,
        local=LocalAgentOptions(cwd=os.getcwd()),
    )
    result = Agent.prompt(prompt, options)
    if getattr(result, "status", None) == "error":
        raise RuntimeError(f"Cursor agent run failed: id={getattr(result, 'id', '?')}")
    return result.result or ""


def _prompt_with_timeout(prompt: str, timeout_ms: int) -> str:
    timeout_s = max(1.0, timeout_ms / 1000.0)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_call_cursor_agent, prompt)
        try:
            return fut.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError as e:
            raise TimeoutError(f"LLM decision timed out after {timeout_ms}ms") from e


def pick_moves_llm(battle) -> tuple[str, str]:
    """Ask Cursor SDK for moves; fall back to heuristic on any failure."""
    if any(battle.force_switch):
        choice_a, choice_b = pick_moves(battle)
        logger.info(
            "Force-switch auto-resolved (heuristic): %s | %s", choice_a, choice_b
        )
        return choice_a, choice_b

    state = build_decision_state(battle)
    legal_a = state["slot_a"]["legal_actions"]
    legal_b = state["slot_b"]["legal_actions"]

    prompt = (
        MOVE_SYSTEM
        + "\n\nBATTLE_STATE:\n"
        + json.dumps(state, separators=(",", ":"))
        + "\n"
    )
    logger.info(
        "LLM move request turn=%s legal_a=%d legal_b=%d",
        battle.turn,
        len(legal_a),
        len(legal_b),
    )

    try:
        raw = _prompt_with_timeout(prompt, FoulPlayConfig.llm_timeout_ms)
        logger.debug("LLM raw response: %s", raw[:1000] if raw else "")
        data = _extract_json(raw)
        if not data:
            raise ValueError("could not parse JSON from LLM response")
        slot_a = str(data.get("slot_a", "")).strip()
        slot_b = str(data.get("slot_b", "")).strip()
        ok, reason = validate_move_choices(slot_a, slot_b, legal_a, legal_b)
        if not ok:
            raise ValueError(reason)
        logger.info(
            "LLM chose turn %s: %s | %s (%s)",
            battle.turn,
            slot_a,
            slot_b,
            data.get("reason", ""),
        )
        return slot_a, slot_b
    except Exception as e:
        logger.warning("LLM move selection failed (%s); using heuristic fallback", e)
        choice_a, choice_b = pick_moves(battle)
        logger.info("Heuristic fallback turn %s: %s | %s", battle.turn, choice_a, choice_b)
        return choice_a, choice_b


def pick_team_preview_digits_llm(battle) -> str:
    """Ask Cursor SDK for team preview order; fall back to heuristic."""
    state = build_team_preview_state(battle)
    legal = state["legal_indices"]
    prompt = (
        PREVIEW_SYSTEM
        + "\n\nTEAM_PREVIEW_STATE:\n"
        + json.dumps(state, separators=(",", ":"))
        + "\n"
    )
    logger.info("LLM team-preview request legal_indices=%s", legal)

    try:
        raw = _prompt_with_timeout(prompt, FoulPlayConfig.llm_timeout_ms)
        logger.debug("LLM preview raw response: %s", raw[:1000] if raw else "")
        data = _extract_json(raw)
        if not data:
            raise ValueError("could not parse JSON from LLM preview response")
        digits = str(data.get("digits", "")).strip()
        ok, reason = validate_team_preview_digits(digits, legal)
        if not ok:
            raise ValueError(reason)
        logger.info(
            "LLM team-preview digits=%s (%s)", digits, data.get("reason", "")
        )
        return digits
    except Exception as e:
        logger.warning(
            "LLM team-preview failed (%s); using heuristic fallback", e
        )
        digits = pick_team_preview_digits(battle)
        logger.info("Heuristic team-preview fallback: %s", digits)
        return digits
