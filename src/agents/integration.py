"""
v2 Multi-Agent production integration layer.

Closes the gap between the v2 framework (`src/agents/*.py` + `src/multi_agent_v2.py`)
and the FastAPI production stack (`src/main.py` + `src/routes/rest.py`).

Per openspec/feat-multi-agent-integration:
- register_all_tools(): inject TOOL_REGISTRY into worker._TOOL_DISPATCH
- setup_v2(): idempotent startup hook (call from main.py)
- is_v2_ready(): status flag for /api/v2/health

Design notes:
- This module is the ONLY place that bridges worker + tools.
- Do NOT import from src.multi_agent (v1) or src.core.session_manager.
- All functions are safe to call from FastAPI startup event handler.
"""
import logging as _logging
from typing import Any

_log = _logging.getLogger(__name__)

# ── Module-level state (idempotency) ──────────────────────────────────────────

_v2_ready: bool = False
_v2_singleton: Any = None  # CompiledStateGraph | None


# ── Public API ────────────────────────────────────────────────────────────────

def register_all_tools() -> int:
    """Register every entry in `src.agents.tools.TOOL_REGISTRY` into the
    worker's runtime dispatch table.

    Returns:
        Number of tools successfully registered (always >= 1, because the
        fallback tool 'web_search' is preserved if present).
    """
    # Lazy imports to avoid pulling langgraph at module import time
    from src.agents import worker
    from src.agents import tools as _tools

    registry = getattr(_tools, "TOOL_REGISTRY", {}) or {}
    registered = 0

    for name, fn in registry.items():
        if name in worker._TOOL_DISPATCH:
            # Idempotent: already registered, skip silently
            continue
        try:
            if not callable(fn):
                raise TypeError(f"tool '{name}' is not callable: {type(fn).__name__}")
            worker.register_tool(name, fn)
            registered += 1
        except Exception as e:
            _log.warning(
                "register_all_tools: skipped '%s' due to %s: %s",
                name, type(e).__name__, e,
            )

    if registered:
        _log.info(
            "v2 tool dispatch: registered %d/%d tools (total in dispatch: %d)",
            registered, len(registry), len(worker._TOOL_DISPATCH),
        )
    return registered


def setup_v2() -> None:
    """Idempotent startup hook. Call from main.py @on_event("startup").

    Order:
      1. register_all_tools() — populates worker dispatch
      2. warm singleton — compiles the langgraph graph

    Safe to call multiple times: subsequent calls return immediately.
    """
    global _v2_ready, _v2_singleton

    if _v2_ready and _v2_singleton is not None:
        _log.debug("setup_v2: already ready, skipping")
        return

    register_all_tools()

    try:
        from src.multi_agent_v2 import get_singleton_multi_agent_v2
        _v2_singleton = get_singleton_multi_agent_v2()
    except Exception as e:
        _log.error("setup_v2: failed to compile v2 graph: %s", e)
        # Leave _v2_ready = False so /api/v2/health reports the failure
        return

    _v2_ready = True
    _log.info("v2 multi-agent ready (graph compiled, tools registered)")


def is_v2_ready() -> bool:
    """Whether setup_v2() has completed successfully."""
    return _v2_ready


def get_v2_singleton():
    """Return the compiled v2 graph (or None if setup not run)."""
    return _v2_singleton


def get_v2_tools_count() -> int:
    """Number of tools currently registered in worker dispatch."""
    from src.agents import worker
    return len(worker._TOOL_DISPATCH)
