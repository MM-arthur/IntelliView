"""
Multi-agent v2 graph: Planner → Workers (parallel via Send) → Reporter.

Spec: openspec/changes/feat-multi-agent/specs/multi-agent/spec.md
      REQ-002 (Send parallel dispatch), REQ-003 (Subgraph isolation)

Topology:
    START
      ↓
    [planner]
      ↓
    [route_to_workers]   ← conditional: returns [Send("worker", t1), Send("worker", t2), ...]
      ↓ (parallel)
    [worker ×N]          ← each runs one task via TOOL_REGISTRY
      ↓ (join)
    [reporter]
      ↓
    END
"""
import logging as _logging
from typing import Dict, Any, List

# LangGraph imports (deferred-safe: graph.py is only imported by tests/agent_driver
# AFTER langgraph is installed, so we fail loudly here if missing)
try:
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import Send
    _LANGGRAPH_OK = True
except ImportError as e:  # pragma: no cover
    _LANGGRAPH_OK = False
    _IMPORT_ERROR = e

# Lazy import: planner/worker/reporter avoid top-level init_llm load (test env)
from src.agents.planner import plan_tasks
from src.agents.worker import run_task
from src.agents.reporter import aggregate_results
from src.agents.tools import TOOL_REGISTRY
from src.core.state import AgentState

_log = _logging.getLogger(__name__)


# ── Node factories (return closures for testability) ──────────────────────────

def build_planner_node():
    """Returns a node fn: state → state with state['tasks'] populated."""
    def planner_node(state: Dict[str, Any]) -> Dict[str, Any]:
        user_query = state.get("user_query", state.get("input_text", ""))
        tasks = plan_tasks(user_query)
        return {**state, "tasks": tasks}
    return planner_node


def build_worker_node():
    """Returns a node fn: single task dict → state with task_results appended."""
    def worker_node(task: Dict[str, Any]) -> Dict[str, Any]:
        result = run_task(task)
        return {"task_results": [result]}
    return worker_node


def build_reporter_node():
    """Returns a node fn: state → state with final_report populated."""
    def reporter_node(state: Dict[str, Any]) -> Dict[str, Any]:
        tasks = state.get("tasks", []) or []
        results = state.get("task_results", []) or []
        errors = state.get("worker_errors", []) or []
        report = aggregate_results(tasks, results, errors)
        return {**state, "final_report": report}
    return reporter_node


# ── Conditional edge: dispatch workers via Send ───────────────────────────────

def route_to_workers(state: Dict[str, Any]) -> List[Send]:
    """Plan's output (list of tasks) → list of Send objects (one per task).

    Each Send carries one task; langgraph dispatches them in parallel to
    the "worker" node, then joins the results into the main state.
    """
    if not _LANGGRAPH_OK:
        raise RuntimeError(f"langgraph not installed: {_IMPORT_ERROR}")
    tasks = state.get("tasks", []) or []
    return [Send("worker", t) for t in tasks]


def planner_to_reporter_or_workers(state: Dict[str, Any]):
    """Decide planner's next stop: workers (if tasks) or reporter (if empty).

    Returns a list of Send (parallel fan-out) or the literal string "reporter".
    langgraph's add_conditional_edges dispatches accordingly.
    """
    if not _LANGGRAPH_OK:
        raise RuntimeError(f"langgraph not installed: {_IMPORT_ERROR}")
    tasks = state.get("tasks", []) or []
    if not tasks:
        return "reporter"
    return [Send("worker", t) for t in tasks]


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_multi_agent_graph():
    """Build and compile the multi-agent graph.

    Returns:
        CompiledStateGraph (langgraph CompiledGraph).
    """
    if not _LANGGRAPH_OK:
        raise RuntimeError(
            f"langgraph not installed: {_IMPORT_ERROR}. "
            "Run: pip install langgraph"
        )

    g = StateGraph(AgentState)

    # Nodes
    g.add_node("planner", build_planner_node())
    g.add_node("worker", build_worker_node())
    g.add_node("reporter", build_reporter_node())

    # Edges
    g.add_edge(START, "planner")
    # Conditional: planner → either fan-out via Send to "worker" (one per task)
    # OR skip workers entirely and go straight to "reporter" if no tasks.
    # The function returns either List[Send] or the literal "reporter" string.
    g.add_conditional_edges("planner", planner_to_reporter_or_workers)
    # All workers converge at reporter
    g.add_edge("worker", "reporter")
    g.add_edge("reporter", END)

    return g.compile()
