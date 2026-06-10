"""
Multi-agent v2 entry points.

Coexists with the original 15-node graph in src.multi_agent.
Old: get_singleton_agent() / create_multi_agent()  → 15-node linear graph
New: get_singleton_multi_agent_v2() / run_multi_agent() → Planner/Workers/Reporter

Per task table #4 risk section: existing run_agent() callers must keep working
until manual switch. Both APIs available; old graph untouched.
"""
import logging as _logging
from typing import Dict, Any, Optional

_log = _logging.getLogger(__name__)

# Lazy imports to avoid loading langgraph at module import time
_v2_graph = None
_planner_node = None
_worker_node = None
_reporter_node = None


def _ensure_v2_loaded():
    """Import graph.py on first call (langgraph is heavy)."""
    global _v2_graph, _planner_node, _worker_node, _reporter_node
    if _v2_graph is None:
        from src.agents.graph import (
            build_multi_agent_graph,
            build_planner_node,
            build_worker_node,
            build_reporter_node,
        )
        _v2_graph = build_multi_agent_graph
        _planner_node = build_planner_node
        _worker_node = build_worker_node
        _reporter_node = build_reporter_node


_singleton_v2 = None


def get_singleton_multi_agent_v2():
    """Process-wide singleton for the v2 graph (matches old get_singleton_agent pattern)."""
    global _singleton_v2
    if _singleton_v2 is None:
        _ensure_v2_loaded()
        _singleton_v2 = _v2_graph()
    return _singleton_v2


def run_multi_agent(
    user_query: str,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the multi-agent v2 graph synchronously.

    Args:
        user_query: The natural-language user request.
        config: Optional langgraph RunnableConfig (e.g. thread_id for checkpointing).

    Returns:
        Final state dict containing tasks / task_results / final_report / etc.
    """
    _ensure_v2_loaded()
    graph = get_singleton_multi_agent_v2()
    input_state = {
        "user_query": user_query,
        "input_text": user_query,  # compat with old state shape
        "tasks": None,
        "task_results": None,
        "worker_errors": None,
        "final_report": None,
        "fallback_used": False,
    }
    return graph.invoke(input_state, config=config or {})


async def astream_multi_agent(
    user_query: str,
    callback,
    config: Optional[Dict[str, Any]] = None,
):
    """Stream v2 graph events via the existing astream_graph driver.

    Reuses src.agent_driver.astream_graph so the frontend (which already handles
    on_tool_end / on_chain_end events) gets the same UX as the old graph.

    Yields raw langgraph events. The callback receives the event dict.
    """
    _ensure_v2_loaded()
    from src.agent_driver import astream_graph

    graph = get_singleton_multi_agent_v2()
    input_state = {
        "user_query": user_query,
        "input_text": user_query,
        "tasks": None,
        "task_results": None,
        "worker_errors": None,
        "final_report": None,
        "fallback_used": False,
    }
    async for event in astream_graph(graph, input_state, callback, config or {}):
        yield event
