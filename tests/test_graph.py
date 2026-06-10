"""
Test graph.py: Subgraph + Send orchestration.

Spec: openspec/changes/feat-multi-agent/specs/multi-agent/spec.md
      REQ-002 (Send parallel dispatch), REQ-003 (Subgraph isolation)
"""
from unittest.mock import patch, MagicMock

# IMPORTANT: patch BEFORE import so init_llm never tries to load
_fake_llm = MagicMock()
_fake_llm.return_value.invoke.return_value.content = "[]"  # planner fallback

with patch("src.agents.planner._init_llm", _fake_llm):
    from src.agents import graph as _graph_module
    from src.agents.graph import (
        build_planner_node,
        build_worker_node,
        build_reporter_node,
        route_to_workers,
        build_multi_agent_graph,
    )


# ── Per-node tests ────────────────────────────────────────────────────────────

def test_planner_node_splits_query_to_tasks():
    """planner_node: take user_query → state.tasks = list of sub-tasks."""
    fake_planner = MagicMock()
    fake_planner.return_value = [
        {"id": "t1", "description": "search", "tool_hint": "web_search"},
    ]
    with patch("src.agents.graph.plan_tasks", fake_planner):
        node = build_planner_node()
        out = node({"user_query": "do something", "tasks": None})

    assert out["tasks"] == [
        {"id": "t1", "description": "search", "tool_hint": "web_search"}
    ]


def test_worker_node_dispatches_to_tool_and_returns_result():
    """worker_node: take single task → invoke tool → return task_result dict."""
    fake_task = {"id": "t1", "description": "search", "tool_hint": "web_search"}
    with patch("src.agents.graph.TOOL_REGISTRY", {"web_search": MagicMock(return_value='{"ok": true}')}):
        with patch("src.agents.graph.run_task") as fake_run:
            fake_run.return_value = {
                "task_id": "t1", "status": "success", "output": "found 3", "error": "", "retries": 0, "fallback_used": False,
            }
            node = build_worker_node()
            out = node(fake_task)

    assert out["task_results"] == [fake_run.return_value]


def test_reporter_node_aggregates_final_report():
    """reporter_node: take tasks + task_results + worker_errors → final_report."""
    with patch("src.agents.graph.aggregate_results") as fake_agg:
        fake_agg.return_value = "# Report\n\nDone"
        node = build_reporter_node()
        out = node({
            "tasks": [{"id": "t1"}],
            "task_results": [{"task_id": "t1", "status": "success"}],
            "worker_errors": [],
        })

    assert out["final_report"] == "# Report\n\nDone"


# ── Conditional edge: route_to_workers ────────────────────────────────────────

def test_route_to_workers_returns_send_per_task():
    """route_to_workers: returns [Send("worker", task)] for each task in state."""
    state = {
        "tasks": [
            {"id": "t1", "description": "a", "tool_hint": "web_search"},
            {"id": "t2", "description": "b", "tool_hint": "rag_processing"},
        ]
    }
    sends = route_to_workers(state)
    assert len(sends) == 2
    # Each Send has node="worker" and the task as arg
    from langgraph.types import Send
    for s in sends:
        assert isinstance(s, Send)
        assert s.node == "worker"
    args = [s.arg for s in sends]
    assert args[0]["id"] == "t1"
    assert args[1]["id"] == "t2"


def test_route_to_workers_empty_tasks_returns_empty_list():
    """route_to_workers: returns [] for empty task list (legacy behavior)."""
    state = {"tasks": []}
    sends = route_to_workers(state)
    assert sends == []


def test_planner_to_reporter_or_workers_empty_routes_to_reporter():
    """planner_to_reporter_or_workers: empty tasks → returns literal 'reporter' string."""
    from src.agents.graph import planner_to_reporter_or_workers
    state = {"tasks": []}
    result = planner_to_reporter_or_workers(state)
    assert result == "reporter"  # string path, not list


def test_planner_to_reporter_or_workers_with_tasks_returns_send_list():
    """planner_to_reporter_or_workers: with tasks → returns List[Send]."""
    from src.agents.graph import planner_to_reporter_or_workers
    state = {
        "tasks": [
            {"id": "t1", "description": "a", "tool_hint": "web_search"},
        ]
    }
    result = planner_to_reporter_or_workers(state)
    assert isinstance(result, list)
    from langgraph.types import Send
    assert isinstance(result[0], Send)


# ── Full graph build + compile ────────────────────────────────────────────────

def test_build_multi_agent_graph_returns_compiled():
    """build_multi_agent_graph returns a compiled langgraph CompiledGraph."""
    g = build_multi_agent_graph()
    # Compiled graph has .invoke and .stream
    assert hasattr(g, "invoke")
    assert hasattr(g, "stream")


def test_full_graph_runs_end_to_end():
    """End-to-end: planner → workers → reporter. All nodes mocked."""
    from src.agents.tools import TOOL_REGISTRY

    fake_tool = MagicMock()
    fake_tool.__name__ = "web_search"
    fake_tool.return_value = '{"ok": true}'

    with patch("src.agents.graph.TOOL_REGISTRY", {"web_search": fake_tool}):
        g = build_multi_agent_graph()
        result = g.invoke({"user_query": "test query", "tasks": None})

    # State should have all multi-agent fields populated
    assert "tasks" in result
    assert "task_results" in result
    assert "final_report" in result
    assert isinstance(result["final_report"], str)
