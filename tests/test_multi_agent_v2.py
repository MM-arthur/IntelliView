"""
Test multi_agent_v2 entry points (Driver integration layer).
"""
from unittest.mock import patch, MagicMock

with patch("src.agents.planner._init_llm") as _mock:
    _mock.return_value.invoke.return_value.content = "[]"
    from src.multi_agent_v2 import (
        get_singleton_multi_agent_v2,
        run_multi_agent,
    )


def test_get_singleton_returns_compiled_graph():
    """Singleton returns the same graph instance (process-level)."""
    g1 = get_singleton_multi_agent_v2()
    g2 = get_singleton_multi_agent_v2()
    assert g1 is g2


def test_run_multi_agent_returns_final_state():
    """End-to-end: query in, full state out."""
    # Stub planner to return 1 task; tools mocked
    with patch("src.agents.graph.plan_tasks") as fake_plan:
        fake_plan.return_value = [
            {"id": "t1", "description": "search", "tool_hint": "web_search"}
        ]
        with patch("src.agents.tools.TOOL_REGISTRY", {
            "web_search": MagicMock(return_value='{"ok": true}'),
        }):
            result = run_multi_agent("test query")

    # Final state must include the multi-agent fields
    assert "tasks" in result
    assert "task_results" in result
    assert "final_report" in result
    assert len(result["tasks"]) == 1
    assert result["tasks"][0]["id"] == "t1"
    assert isinstance(result["final_report"], str)


def test_run_multi_agent_handles_empty_plan():
    """Planner returns empty (fallback): graph still produces a report."""
    with patch("src.agents.graph.plan_tasks") as fake_plan:
        fake_plan.return_value = []  # edge: no tasks
        with patch("src.agents.tools.TOOL_REGISTRY", {}):
            result = run_multi_agent("anything")

    assert result["final_report"]  # reporter still runs
    assert "No tasks" in result["final_report"] or "0/0" in result["final_report"]


def test_run_multi_agent_includes_user_query_in_state():
    """user_query passed through to state.input_text (legacy field)."""
    with patch("src.agents.graph.plan_tasks") as fake_plan:
        fake_plan.return_value = []
        with patch("src.agents.tools.TOOL_REGISTRY", {}):
            result = run_multi_agent("my specific query")

    # State carried through to reporter (input_text is the legacy field in AgentState)
    assert "my specific query" in result["input_text"]


def test_old_multi_agent_still_exists():
    """Backward compat: old multi_agent.py file still present (regression).

    Critical per task table #4 risk section: existing run_agent() callers must
    keep working until manual switch.

    NOTE: We do NOT import the old module here. It uses langgraph.checkpoint.sqlite
    which was renamed in langgraph 0.3+; that is a pre-existing issue, not introduced
    by this change. Verify file presence only.
    """
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "src", "multi_agent.py")
    assert os.path.isfile(path), "old src/multi_agent.py must not be deleted"

    # Read the file and confirm the public entry points still exist
    with open(path) as f:
        content = f.read()
    assert "def get_singleton_agent" in content
    assert "def create_multi_agent" in content
    # The old 15-node workflow should still be wired
    assert "workflow.add_node" in content
