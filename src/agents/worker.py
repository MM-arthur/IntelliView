"""
Worker node: execute a single task.

Issue #4: Multi-agent v2 architecture.
Spec: openspec/changes/feat-multi-agent/specs/multi-agent/spec.md

Decoupling: Worker uses an injectable _TOOL_DISPATCH dict so it can
be unit-tested without loading MCP servers.
"""
import logging as _logging
from typing import Dict, Any, Callable, Optional

_log = _logging.getLogger(__name__)

# Retry policy per design.md §4
_MAX_RETRIES = 3

# Default fallback tool when tool_hint is unknown
_FALLBACK_TOOL = "web_search"

# Tool dispatch registry. Tests patch this; production loads MCP tools.
# Format: {"tool_name": callable_that_takes(str) -> str}
_TOOL_DISPATCH: Dict[str, Callable[[str], str]] = {}


def register_tool(name: str, fn: Callable[[str], str]) -> None:
    """Register a tool (production hook, called at startup)."""
    _TOOL_DISPATCH[name] = fn


def _empty_result(task_id: str) -> Dict[str, Any]:
    """Stable shape per spec: every Worker result has these keys."""
    return {
        "task_id": task_id,
        "status": "error",
        "output": "",
        "error": "",
        "retries": 0,
        "fallback_used": False,
    }


def _invoke_with_retry(tool_fn: Callable, query: str) -> str:
    """Call tool up to _MAX_RETRIES times. Re-raise final exception.

    Tool protocol: tool_fn.invoke(query) returns the result (langchain Tool style).
    """
    last_err: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES):
        try:
            # Support both callable and .invoke() (langchain Tool)
            if hasattr(tool_fn, "invoke"):
                return tool_fn.invoke(query)
            return tool_fn(query)
        except Exception as e:
            last_err = e
            _log.warning("Worker tool attempt %d/%d failed: %s", attempt + 1, _MAX_RETRIES, e)
    raise last_err  # type: ignore[misc]


def run_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """Run a single task: route → invoke (with retry) → return result.

    Args:
        task: {"id", "description", "tool_hint"}

    Returns:
        {"task_id", "status", "output", "error", "retries", "fallback_used"}
    """
    task_id = task.get("id", "t_unknown")
    description = task.get("description", "")
    tool_hint = task.get("tool_hint", _FALLBACK_TOOL)

    result = _empty_result(task_id)

    # Pick tool. Fall back to _FALLBACK_TOOL if hint not registered.
    fallback_used = False
    if tool_hint in _TOOL_DISPATCH:
        tool_name = tool_hint
    elif _FALLBACK_TOOL in _TOOL_DISPATCH:
        tool_name = _FALLBACK_TOOL
        fallback_used = True
    else:
        # No tool available at all
        result["error"] = f"tool '{tool_hint}' not registered and no fallback available"
        return result

    tool_fn = _TOOL_DISPATCH[tool_name]
    result["fallback_used"] = fallback_used

    try:
        output = _invoke_with_retry(tool_fn, description)
        result["status"] = "success"
        result["output"] = str(output)
        result["retries"] = 0  # success on first try
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        result["retries"] = _MAX_RETRIES

    return result
