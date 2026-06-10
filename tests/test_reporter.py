"""
RED phase 4: test Reporter behavior.

Reporter takes Planner tasks + Worker results + Worker errors, aggregates
into a final Markdown report. Pure function - no LLM calls.
"""
from src.agents.reporter import aggregate_results


def test_reporter_aggregates_all_success():
    """All tasks succeed → final report lists all results."""
    tasks = [
        {"id": "t1", "description": "Find Python jobs", "tool_hint": "web_search"},
        {"id": "t2", "description": "Parse results", "tool_hint": "rag_search"},
    ]
    results = [
        {"task_id": "t1", "status": "success", "output": "Found 3 jobs", "error": "", "retries": 0, "fallback_used": False},
        {"task_id": "t2", "status": "success", "output": "Parsed JSON", "error": "", "retries": 0, "fallback_used": False},
    ]
    report = aggregate_results(tasks, results, [])
    assert "Found 3 jobs" in report
    assert "Parsed JSON" in report
    assert "t1" in report
    assert "t2" in report


def test_reporter_marks_partial_failure():
    """Some tasks fail → report includes failure note but still aggregates."""
    tasks = [
        {"id": "t1", "description": "Search", "tool_hint": "web_search"},
        {"id": "t2", "description": "Parse", "tool_hint": "rag_search"},
    ]
    results = [
        {"task_id": "t1", "status": "success", "output": "ok", "error": "", "retries": 0, "fallback_used": False},
        {"task_id": "t2", "status": "error", "output": "", "error": "timeout", "retries": 3, "fallback_used": True},
    ]
    report = aggregate_results(tasks, results, [])
    assert "ok" in report
    assert "timeout" in report or "失败" in report or "error" in report.lower()
    # Both tasks still represented
    assert "t1" in report
    assert "t2" in report


def test_reporter_handles_all_failure():
    """All tasks fail → report still generated (degraded mode)."""
    tasks = [
        {"id": "t1", "description": "Search", "tool_hint": "web_search"},
    ]
    results = [
        {"task_id": "t1", "status": "error", "output": "", "error": "API down", "retries": 3, "fallback_used": True},
    ]
    report = aggregate_results(tasks, results, [])
    assert "API down" in report or "down" in report
    assert "t1" in report


def test_reporter_includes_task_descriptions():
    """Report uses Planner task descriptions as section headers."""
    tasks = [
        {"id": "t1", "description": "Find Python jobs in Beijing", "tool_hint": "web_search"},
    ]
    results = [
        {"task_id": "t1", "status": "success", "output": "5 results", "error": "", "retries": 0, "fallback_used": False},
    ]
    report = aggregate_results(tasks, results, [])
    # Description appears as section header
    assert "Find Python jobs" in report


def test_reporter_includes_worker_errors():
    """worker_errors list is included in the report (audit trail)."""
    errors = [
        {"task_id": "t1", "error": "rate limit", "retries": 3},
    ]
    report = aggregate_results([], [], errors)
    assert "rate limit" in report or "t1" in report


def test_reporter_output_is_markdown():
    """Report is valid Markdown (has headings or structure)."""
    tasks = [{"id": "t1", "description": "Search", "tool_hint": "web_search"}]
    results = [
        {"task_id": "t1", "status": "success", "output": "ok", "error": "", "retries": 0, "fallback_used": False},
    ]
    report = aggregate_results(tasks, results, [])
    # Markdown markers (##, -, etc.) present
    assert any(marker in report for marker in ("##", "###", "-", "*", "\n"))


def test_reporter_handles_empty_inputs():
    """No tasks: report is short, not crashing."""
    report = aggregate_results([], [], [])
    assert isinstance(report, str)
    assert len(report) > 0  # at least a header
