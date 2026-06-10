"""
Tool wrappers for original 15 nodes.

Phase 1-Worker demo: wrap behavior_detection first (simplest, representative).
Spec: REQ-001 "原 node 改 Tool 后行为必须等价"

Design:
- Tool functions take a single string input, return JSON string output (langchain Tool contract)
- They delegate to the original node, extracting the relevant result field
- They NEVER mutate the original node signature (langgraph graph still uses it)
- Failures are caught and returned as {"success": false, "error": "..."} JSON
"""
import json as _json
import logging as _logging
from typing import Callable

_log = _logging.getLogger(__name__)


def _wrap_node_as_tool(
    node_fn: Callable,
    input_field: str,
    result_field: str,
) -> Callable[[str], str]:
    """Generic wrapper: input_str → state with input_field set → node(state) → result_field JSON.

    Args:
        node_fn: Original langgraph node (state) -> state.
        input_field: State key the node reads from (e.g. "video_frame_data").
        result_field: State key the node writes to (e.g. "behavior_result").
    """
    def tool(input_str: str) -> str:
        state = {input_field: input_str}
        try:
            out = node_fn(state)
            result = out.get(result_field, {"success": False, "error": "no result field"})
        except Exception as e:
            _log.warning("Tool wrapper for %s failed: %s", node_fn.__name__, e)
            result = {"success": False, "error": f"{type(e).__name__}: {e}"}
        return _json.dumps(result, ensure_ascii=False)
    tool.__name__ = f"{node_fn.__name__}_tool"
    return tool


# Lazy import: original nodes import langgraph (heavy chain). Defer until tool is called.
# Exposed as module attributes so tests can patch them with `patch("src.agents.tools.X")`.
import sys as _sys

# Module-level proxy. Tests patch this attribute directly:
#   with patch("src.agents.tools.behavior_detection", return_value=fake_node):
# The proxy must read the *module attribute* (not a closure) so patches are honored.
def _behavior_detection_proxy(state):
    # Look up the current module attribute at call time (this is what patch() swaps).
    current = getattr(_sys.modules[__name__], "behavior_detection", _behavior_detection_proxy)
    if current is not _behavior_detection_proxy:
        return current(state)
    # Fallback: real import (first call, or after patch was removed)
    from src.nodes.generation import behavior_detection as _real_node
    return _real_node(state)


# Bind proxy to module attribute so patch() can find/replace it.
behavior_detection = _behavior_detection_proxy  # type: ignore[assignment]


def behavior_detection_tool(input_str: str) -> str:
    """Run YOLO behavior analysis on a video frame (base64-encoded).

    Args:
        input_str: Base64-encoded video frame data.

    Returns:
        JSON string of the analysis result (e.g. {"success": true, "behavior": "..."}).
    """
    wrapper = _wrap_node_as_tool(behavior_detection, "video_frame_data", "behavior_result")
    return wrapper(input_str)
