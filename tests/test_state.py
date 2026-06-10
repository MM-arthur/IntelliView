"""
RED phase 1: test AgentState TypedDict has multi-agent fields.

TDD rule: write the simplest test that fails first. This test asserts
the new fields exist on AgentState. It will fail until state.py is
updated correctly.
"""
from src.core.state import AgentState


def test_agent_state_has_tasks_field():
    """Planner output: list of sub-tasks. Required for #4 multi-agent."""
    state: AgentState = {
        "tasks": [{"id": "t1", "description": "Find Python jobs"}],
    }
    assert state["tasks"] is not None
    assert len(state["tasks"]) == 1
    assert state["tasks"][0]["id"] == "t1"


def test_agent_state_has_task_results_field():
    """Worker outputs aggregated. Required for #4 multi-agent."""
    state: AgentState = {
        "task_results": [
            {"task_id": "t1", "output": "Found 3 jobs", "status": "success"}
        ],
    }
    assert state["task_results"][0]["status"] == "success"


def test_agent_state_has_worker_errors_field():
    """Error tracking per worker. Required for retry/fallback logic."""
    state: AgentState = {
        "worker_errors": [{"task_id": "t1", "error": "timeout", "retries": 3}],
    }
    assert state["worker_errors"][0]["retries"] == 3


def test_agent_state_has_final_report_field():
    """Reporter aggregated output. Top-level result of multi-agent run."""
    state: AgentState = {
        "final_report": "## Summary\nFound 3 jobs across 2 sources",
    }
    assert "Summary" in state["final_report"]


def test_agent_state_has_fallback_used_field():
    """Boolean flag: did any task fall back to default? Audit trail."""
    state: AgentState = {
        "fallback_used": True,
    }
    assert state["fallback_used"] is True


def test_agent_state_supports_full_multi_agent_shape():
    """Integration: all multi-agent fields coexist in one state dict."""
    state: AgentState = {
        # Pre-existing fields (smoke-test backward compat)
        "job_title": "AI Engineer",
        "review_report": None,
        "career_plan": None,
        # New multi-agent fields
        "tasks": [{"id": "t1", "description": "Search jobs"}],
        "task_results": [{"task_id": "t1", "output": "ok", "status": "success"}],
        "worker_errors": [],
        "final_report": "Done",
        "fallback_used": False,
    }
    # All fields present and typed correctly
    assert isinstance(state["tasks"], list)
    assert isinstance(state["task_results"], list)
    assert isinstance(state["worker_errors"], list)
    assert isinstance(state["final_report"], str)
    assert isinstance(state["fallback_used"], bool)
    # Backward compat intact
    assert state["job_title"] == "AI Engineer"
