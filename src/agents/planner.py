"""
Planner node: split user query into 1-5 sub-tasks.

Issue #4: Multi-agent v2 architecture (Planner / Workers / Reporter).
Spec: openspec/changes/feat-multi-agent/specs/multi-agent/spec.md
Design: openspec/changes/feat-multi-agent/design.md §3

This module is intentionally decoupled from src.multi_agent so it can
be unit-tested without loading the full LangGraph stack.
"""
import json as _json
import re as _re
import logging as _logging
from typing import List, Dict, Any, Optional

_log = _logging.getLogger(__name__)

# Capped at 5 per design.md §3 (Worker count)
_MAX_TASKS = 5

# Lazy import: avoid hard-fail if init_llm not configured in test env
try:
    from src.core.llm import init_llm as _init_llm
except ImportError:
    _init_llm = None  # type: ignore


def _strip_markdown_fence(text: str) -> str:
    """Extract JSON from ```json ... ``` blocks. LLM decoration."""
    m = _re.search(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", text, _re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()


def _normalize_task(raw: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Ensure every task has id / description / tool_hint. Fill defaults if missing."""
    return {
        "id": raw.get("id") or f"t{index + 1}",
        "description": raw.get("description") or "",
        "tool_hint": raw.get("tool_hint") or "web_search",
    }


def _parse_tasks_from_llm(content: str) -> List[Dict[str, Any]]:
    """Parse LLM content → list of task dicts. Empty list on garbage."""
    try:
        data = _json.loads(content)
    except (_json.JSONDecodeError, TypeError):
        return []

    if isinstance(data, dict) and "tasks" in data:
        data = data["tasks"]

    if not isinstance(data, list):
        return []

    out = []
    for i, item in enumerate(data):
        if isinstance(item, dict):
            out.append(_normalize_task(item, i))
    return out


def _fallback_task(user_query: str) -> List[Dict[str, Any]]:
    """Last-resort single task when LLM gives nothing usable."""
    return [{
        "id": "t1",
        "description": user_query or "(no query provided)",
        "tool_hint": "web_search",
    }]


def plan_tasks(user_query: str, llm: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Planner: split a user query into 1-5 sub-tasks.

    Args:
        user_query: Natural-language user request.
        llm: Optional pre-built LLM. Defaults to init_llm() (Moonshot).

    Returns:
        List of {"id", "description", "tool_hint"} dicts. Always non-empty.
        On any failure, returns [_fallback_task(user_query)].
    """
    if not user_query or not user_query.strip():
        return _fallback_task("")

    if llm is None:
        if _init_llm is None:
            _log.warning("init_llm unavailable; returning fallback task")
            return _fallback_task(user_query)
        try:
            llm = _init_llm()
        except Exception as e:
            _log.warning("init_llm() failed: %s; returning fallback", e)
            return _fallback_task(user_query)

    prompt = (
        "You are a task planner. Split the user query into 1-5 concrete sub-tasks.\n"
        "Return ONLY a JSON array. Each item: "
        '{"id": "t1", "description": "...", "tool_hint": "web_search|rag_search|document_parse|behavior_detection|mock_interview"}.\n'
        f"User query: {user_query}\n"
        "Tasks:"
    )

    try:
        resp = llm.invoke(prompt)
        content = getattr(resp, "content", str(resp))
    except Exception as e:
        _log.warning("LLM invoke failed: %s; returning fallback", e)
        return _fallback_task(user_query)

    cleaned = _strip_markdown_fence(content)
    tasks = _parse_tasks_from_llm(cleaned)

    if not tasks:
        return _fallback_task(user_query)

    # Cap at _MAX_TASKS, re-number
    tasks = tasks[:_MAX_TASKS]
    for i, t in enumerate(tasks):
        t["id"] = f"t{i + 1}"
    return tasks
