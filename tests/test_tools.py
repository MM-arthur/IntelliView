"""
Test Tool wrappers for 14 nodes.

Phase 2: expand to all 14 wrappable nodes.
Spec: REQ-001 "原 node 改 Tool 后行为必须等价"
"""
import json
from unittest.mock import patch, MagicMock

from src.agents import tools as _tools_module
from src.agents.tools import (
    pre_router_tool, ocr_processing_tool, document_parsing_tool,
    process_speech_to_text_tool, optimize_transcript_tool, rag_processing_tool,
    web_search_tool, generate_response_tool, behavior_detection_tool,
    intent_recognition_tool, agent_router_tool, mock_interview_tool,
    interview_review_tool, career_planning_tool, TOOL_REGISTRY,
)


def _patched_node(name, return_value):
    """Patch the node proxy in tools module to return a fixed value."""
    fake = MagicMock()
    fake.__name__ = name
    fake.return_value = return_value
    return patch(f"src.agents.tools.{name}", fake)


# ── Tool registry completeness ────────────────────────────────────────────────

def test_tool_registry_has_14_tools():
    """All 14 wrappable nodes are exposed in TOOL_REGISTRY."""
    expected = {
        "pre_router", "ocr_processing", "document_parsing",
        "process_speech_to_text", "optimize_transcript", "rag_processing",
        "web_search", "generate_response", "behavior_detection",
        "intent_recognition", "agent_router", "mock_interview",
        "interview_review", "career_planning",
    }
    assert set(TOOL_REGISTRY.keys()) == expected


def test_tool_registry_values_are_callables():
    """All registered tools are callable (langchain Tool contract)."""
    for name, fn in TOOL_REGISTRY.items():
        assert callable(fn), f"{name} is not callable"


# ── Per-tool sanity tests (one per Tool) ───────────────────────────────────────

def test_pre_router_tool():
    with _patched_node("pre_router", {"pre_route": "vision"}):
        out = pre_router_tool("test input")
    assert json.loads(out) == "vision"


def test_ocr_processing_tool():
    with _patched_node("ocr_processing", {"ocr_result": "extracted text"}):
        out = ocr_processing_tool("/tmp/img.png")
    assert json.loads(out) == "extracted text"


def test_document_parsing_tool():
    with _patched_node("document_parsing", {"parsed_document": {"pages": 3}}):
        out = document_parsing_tool("/tmp/doc.pdf")
    assert json.loads(out) == {"pages": 3}


def test_process_speech_to_text_tool():
    with _patched_node("process_speech_to_text", {"transcript": "hello world"}):
        out = process_speech_to_text_tool("/tmp/audio.wav")
    assert json.loads(out) == "hello world"


def test_optimize_transcript_tool():
    with _patched_node("optimize_transcript", {"optimized_text": "Hello, world."}):
        out = optimize_transcript_tool("hello world")
    assert json.loads(out) == "Hello, world."


def test_rag_processing_tool():
    with _patched_node("rag_processing", {"rag_result": "context", "rag_sources": ["s1"]}):
        out = rag_processing_tool("query")
    parsed = json.loads(out)
    assert parsed["rag_result"] == "context"
    assert parsed["rag_sources"] == ["s1"]


def test_web_search_tool():
    with _patched_node("web_search", {"web_search_result": "found 3", "web_sources": ["u1"]}):
        out = web_search_tool("query")
    parsed = json.loads(out)
    assert parsed["web_search_result"] == "found 3"
    assert parsed["web_sources"] == ["u1"]


def test_generate_response_tool():
    with _patched_node("generate_response", {"response": "answer", "history": []}):
        out = generate_response_tool("context")
    parsed = json.loads(out)
    assert parsed["response"] == "answer"
    assert parsed["history"] == []


def test_behavior_detection_tool():
    with _patched_node("behavior_detection", {"behavior_result": {"success": True, "behavior": "smiling"}}):
        out = behavior_detection_tool("base64")
    assert json.loads(out) == {"success": True, "behavior": "smiling"}


def test_intent_recognition_tool():
    with _patched_node("intent_recognition", {"intent": {"question_type": "技术问题"}}):
        out = intent_recognition_tool("transcript")
    assert json.loads(out) == {"question_type": "技术问题"}


def test_agent_router_tool():
    with _patched_node("agent_router", {"intent_mode": "mock_interview"}):
        out = agent_router_tool(json.dumps({"question_type": "技术问题"}))
    assert json.loads(out) == {"intent_mode": "mock_interview"}


def test_agent_router_tool_handles_bad_json():
    """Invalid JSON in input: graceful fallback (no crash)."""
    with _patched_node("agent_router", {"intent_mode": "normal_chat"}):
        out = agent_router_tool("not json")
    assert json.loads(out) == {"intent_mode": "normal_chat"}


def test_mock_interview_tool():
    with _patched_node("mock_interview", {"response": "Tell me about...", "interview_history": [], "history": []}):
        out = mock_interview_tool("candidate answer")
    parsed = json.loads(out)
    assert parsed["response"] == "Tell me about..."


def test_interview_review_tool():
    with _patched_node("interview_review", {"review_report": "Good.", "response": "ok"}):
        out = interview_review_tool("transcript")
    parsed = json.loads(out)
    assert parsed["review_report"] == "Good."


def test_career_planning_tool():
    with _patched_node("career_planning", {"career_plan": "1. Learn Python..."}):
        out = career_planning_tool("profile")
    assert json.loads(out) == {"career_plan": "1. Learn Python..."}


# ── Universal error handling: all tools catch exceptions ──────────────────────

def test_all_tools_catch_exceptions():
    """Every tool returns error JSON (not raises) when its node explodes."""
    # Pick a few representative tools
    for node_name in ("optimize_transcript", "rag_processing", "web_search", "mock_interview"):
        fake = MagicMock()
        fake.__name__ = node_name
        fake.side_effect = RuntimeError(f"{node_name} crashed")
        with patch(f"src.agents.tools.{node_name}", fake):
            tool_fn = TOOL_REGISTRY[node_name]
            out = tool_fn("input")
            parsed = json.loads(out)
            assert parsed["success"] is False
            assert "crashed" in parsed["error"] or "RuntimeError" in parsed["error"]
