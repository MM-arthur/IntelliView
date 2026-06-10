"""
RED phase 3: test Worker behavior.

Worker takes a single task dict, routes to the right tool, executes, returns result.
We test routing + retry + fallback logic with a fake _TOOL_DISPATCH dict.
"""
from unittest.mock import patch, MagicMock

from src.agents.worker import run_task


def _make_tool(name, return_value=None, raises=None):
    """Create a fake tool."""
    tool = MagicMock()
    tool.name = name
    if raises is not None:
        tool.invoke.side_effect = raises
    else:
        tool.invoke.return_value = return_value
    return tool


def test_worker_routes_web_search():
    """tool_hint=web_search → web_search tool gets called."""
    fake_tool = _make_tool("web_search", return_value="Found 3 results")
    with patch("src.agents.worker._TOOL_DISPATCH", {"web_search": fake_tool}):
        result = run_task({
            "id": "t1",
            "description": "Search for Python jobs",
            "tool_hint": "web_search",
        })
    assert result["task_id"] == "t1"
    assert result["status"] == "success"
    assert result["output"] == "Found 3 results"
    assert not result["error"]  # falsy (None or "")
    fake_tool.invoke.assert_called_once()


def test_worker_routes_rag_search():
    """tool_hint=rag_search → rag_search tool gets called."""
    fake_tool = _make_tool("rag_search", return_value="From RAG index")
    with patch("src.agents.worker._TOOL_DISPATCH", {"rag_search": fake_tool}):
        result = run_task({
            "id": "t2",
            "description": "Query RAG",
            "tool_hint": "rag_search",
        })
    assert result["task_id"] == "t2"
    assert result["status"] == "success"
    assert result["output"] == "From RAG index"
    fake_tool.invoke.assert_called_once()


def test_worker_retries_on_tool_failure():
    """Tool raises: worker retries 3 times before giving up."""
    fake_tool = _make_tool("web_search", raises=RuntimeError("network timeout"))
    with patch("src.agents.worker._TOOL_DISPATCH", {"web_search": fake_tool}):
        result = run_task({
            "id": "t3",
            "description": "Search",
            "tool_hint": "web_search",
        })
    assert result["status"] == "error"
    assert "timeout" in result["error"]
    assert result["retries"] == 3
    assert fake_tool.invoke.call_count == 3


def test_worker_falls_back_to_default_tool_on_unknown_hint():
    """Unknown tool_hint: use web_search as fallback (not crash)."""
    fake_tool = _make_tool("web_search", return_value="Fallback result")
    with patch("src.agents.worker._TOOL_DISPATCH", {"web_search": fake_tool}):
        result = run_task({
            "id": "t4",
            "description": "Do something",
            "tool_hint": "nonexistent_tool",
        })
    # Either succeeds via fallback OR returns error with clear message
    assert result["status"] in ("success", "error")
    assert result["fallback_used"] is True


def test_worker_returns_error_if_tool_missing():
    """Tool not registered + no fallback available: return error, don't crash."""
    with patch("src.agents.worker._TOOL_DISPATCH", {}):  # empty dispatch
        result = run_task({
            "id": "t5",
            "description": "X",
            "tool_hint": "web_search",
        })
    assert result["status"] == "error"
    assert "not registered" in result["error"].lower() or "not found" in result["error"].lower()
    assert result["retries"] == 0


def test_worker_result_shape_is_stable():
    """All Worker results have the same keys (Planner/Reporter rely on this)."""
    fake_tool = _make_tool("web_search", return_value="ok")
    with patch("src.agents.worker._TOOL_DISPATCH", {"web_search": fake_tool}):
        result = run_task({
            "id": "t6",
            "description": "X",
            "tool_hint": "web_search",
        })
    for key in ("task_id", "status", "output", "error", "retries", "fallback_used"):
        assert key in result, f"missing key: {key}"
