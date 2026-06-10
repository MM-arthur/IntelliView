"""
Reporter node: aggregate Worker results into a Markdown report.

Issue #4: Multi-agent v2 architecture.
Spec: openspec/changes/feat-multi-agent/specs/multi-agent/spec.md

Pure function: takes inputs, returns Markdown string. No LLM, no I/O.
"""
from typing import List, Dict, Any


def _status_icon(status: str, fallback_used: bool) -> str:
    """Visual status indicator."""
    if status == "success":
        return "[OK]" if not fallback_used else "[OK/FALLBACK]"
    return "[FAIL]"


def _format_result_block(task: Dict[str, Any], result: Dict[str, Any]) -> str:
    """One section per task: header + status + output/error."""
    task_id = task.get("id", result.get("task_id", "?"))
    desc = task.get("description", "")
    status = result.get("status", "error")
    fallback = result.get("fallback_used", False)
    icon = _status_icon(status, fallback)

    lines = [f"### {icon} {task_id}: {desc}"]
    if status == "success":
        lines.append("")
        lines.append(result.get("output", ""))
    else:
        err = result.get("error", "unknown error")
        retries = result.get("retries", 0)
        lines.append("")
        lines.append(f"**Error** (after {retries} retries): {err}")
    return "\n".join(lines)


def _format_worker_errors(worker_errors: List[Dict[str, Any]]) -> str:
    """Audit-trail section for per-worker errors."""
    if not worker_errors:
        return ""
    lines = ["## Worker Errors", ""]
    for e in worker_errors:
        task_id = e.get("task_id", "?")
        err = e.get("error", "")
        retries = e.get("retries", 0)
        lines.append(f"- **{task_id}**: {err} (retries: {retries})")
    return "\n".join(lines)


def aggregate_results(
    tasks: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    worker_errors: List[Dict[str, Any]],
) -> str:
    """Aggregate Planner tasks + Worker results + Worker errors into Markdown.

    Args:
        tasks: Planner output (list of {"id", "description", "tool_hint"}).
        results: Worker outputs (list of {"task_id", "status", "output", ...}).
        worker_errors: Per-worker error audit (list of {"task_id", "error", "retries"}).

    Returns:
        Markdown string. Always non-empty (at least a header).
    """
    # Build task_id → result map for safe lookup
    results_by_id: Dict[str, Dict[str, Any]] = {
        r.get("task_id", ""): r for r in results
    }

    # Summary stats
    total = len(tasks)
    succeeded = sum(1 for r in results if r.get("status") == "success")
    failed = total - succeeded

    lines = ["# Multi-Agent Report", ""]
    lines.append(f"**Summary**: {succeeded}/{total} tasks succeeded, {failed} failed")
    lines.append("")

    if not tasks:
        lines.append("_No tasks were planned._")
    else:
        for task in tasks:
            task_id = task.get("id", "?")
            result = results_by_id.get(task_id)
            if result is None:
                # Task planned but no result - treat as failure
                result = {
                    "task_id": task_id,
                    "status": "error",
                    "output": "",
                    "error": "no result returned",
                    "retries": 0,
                    "fallback_used": False,
                }
            lines.append(_format_result_block(task, result))
            lines.append("")

    worker_err_section = _format_worker_errors(worker_errors)
    if worker_err_section:
        lines.append(worker_err_section)

    return "\n".join(lines).rstrip() + "\n"
