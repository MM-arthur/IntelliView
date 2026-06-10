"""
RED phase 2: test Planner behavior.

Planner takes a user query and returns a list of sub-tasks.
We mock the LLM so we test planner LOGIC, not LLM internals.
"""
from unittest.mock import patch
import json

from src.agents.planner import plan_tasks


def _fake_llm_response(content_str: str):
    """Build a fake LLM that returns a given JSON string."""
    class FakeResp:
        def __init__(self, c):
            self.content = c
    class FakeLLM:
        def invoke(self, *args, **kwargs):
            return FakeResp(content_str)
    return FakeLLM()


def test_planner_returns_list_of_tasks():
    """Happy path: LLM returns valid JSON, planner returns list of dicts."""
    llm_output = json.dumps([
        {"id": "t1", "description": "Search Python jobs", "tool_hint": "web_search"},
        {"id": "t2", "description": "Parse results", "tool_hint": "rag_search"},
    ])
    with patch("src.agents.planner._init_llm", return_value=_fake_llm_response(llm_output)):
        tasks = plan_tasks("Find me AI engineer jobs in Beijing")

    assert isinstance(tasks, list)
    assert len(tasks) == 2
    assert tasks[0]["id"] == "t1"
    assert tasks[0]["description"] == "Search Python jobs"
    assert tasks[0]["tool_hint"] == "web_search"
    assert tasks[1]["id"] == "t2"


def test_planner_returns_at_most_five_tasks():
    """Cap: even if LLM hallucinates 10, we cap at 5."""
    llm_output = json.dumps([
        {"id": f"t{i}", "description": f"task {i}", "tool_hint": "web_search"}
        for i in range(10)
    ])
    with patch("src.agents.planner._init_llm", return_value=_fake_llm_response(llm_output)):
        tasks = plan_tasks("do 10 things")

    assert len(tasks) <= 5


def test_planner_fallback_on_invalid_json():
    """If LLM returns garbage, fall back to a single generic task."""
    with patch("src.agents.planner._init_llm", return_value=_fake_llm_response("not json at all")):
        tasks = plan_tasks("anything")

    # Fallback: 1 task with the raw query as description
    assert len(tasks) == 1
    assert tasks[0]["id"] == "t1"
    assert "anything" in tasks[0]["description"].lower() or tasks[0]["description"]  # non-empty


def test_planner_assigns_ids_when_missing():
    """If LLM omits 'id', planner assigns t1, t2, t3 automatically."""
    llm_output = json.dumps([
        {"description": "First", "tool_hint": "web_search"},
        {"description": "Second", "tool_hint": "rag_search"},
    ])
    with patch("src.agents.planner._init_llm", return_value=_fake_llm_response(llm_output)):
        tasks = plan_tasks("do two things")

    assert tasks[0]["id"] == "t1"
    assert tasks[1]["id"] == "t2"


def test_planner_fallback_on_llm_exception():
    """If LLM call raises, planner returns a single fallback task."""
    class ExplodingLLM:
        def invoke(self, *args, **kwargs):
            raise RuntimeError("API down")

    with patch("src.agents.planner._init_llm", return_value=ExplodingLLM()):
        tasks = plan_tasks("anything")

    # Fallback: 1 task, no crash
    assert len(tasks) == 1
    assert tasks[0]["id"] == "t1"


def test_planner_extracts_json_from_markdown_fence():
    """LLMs often wrap JSON in ```json ... ```. Planner should strip it."""
    llm_output = """```json
[
  {"id": "t1", "description": "Search", "tool_hint": "web_search"}
]
```"""
    with patch("src.agents.planner._init_llm", return_value=_fake_llm_response(llm_output)):
        tasks = plan_tasks("search something")

    assert len(tasks) == 1
    assert tasks[0]["id"] == "t1"
