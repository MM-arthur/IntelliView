"""
Tool wrappers for original 15 nodes.

Phase: expand from 1 (behavior_detection) to 13 of 15 nodes.
The 2 unwrapped: check_rag_result (langgraph edge function, returns str not state)
                  _get_intent_mode (private helper)

Spec: REQ-001 "原 node 改 Tool 后行为必须等价"

Design:
- Tool input: single string, output: JSON string (langchain Tool contract)
- They delegate to the original node, extracting the relevant result field
- Original node signature is unchanged (langgraph graph still uses it)
- Failures → {"success": false, "error": "..."} JSON
"""
import json as _json
import logging as _logging
import sys as _sys
from typing import Callable

_log = _logging.getLogger(__name__)


def _wrap_node_as_tool(
    node_fn: Callable,
    input_field: str,
    result_field: str,
) -> Callable[[str], str]:
    """Generic: input_str → state with input_field set → node(state) → result_field JSON."""
    def tool(input_str: str) -> str:
        state = {input_field: input_str}
        try:
            out = node_fn(state)
            result = out.get(result_field, {"success": False, "error": "no result field"})
        except Exception as e:
            _log.warning("Tool wrapper for %s failed: %s", node_fn.__name__, e)
            result = {"success": False, "error": f"{type(e).__name__}: {e}"}
        return _json.dumps(result, ensure_ascii=False)
    tool.__name__ = f"{node_fn.__name__}_tool"
    return tool


def _make_proxy(name: str, import_path: str):
    """Build a module-level proxy that reads sys.modules[name] at call time.

    Tests patch() the module attribute; the proxy must honor that.
    """
    def proxy(state):
        current = getattr(_sys.modules[__name__], name, None)
        if current is not None and current is not proxy:
            return current(state)
        # First call: import the real node and bind it
        mod_path, attr = import_path.rsplit(".", 1)
        import importlib
        mod = importlib.import_module(mod_path)
        real = getattr(mod, attr)
        setattr(_sys.modules[__name__], name, real)
        return real(state)
    proxy.__name__ = name
    return proxy


# ── Module-level proxy attributes (for test patching) ──────────────────────────
pre_router = _make_proxy("pre_router", "src.nodes.preprocessing.pre_router")
ocr_processing = _make_proxy("ocr_processing", "src.nodes.preprocessing.ocr_processing")
document_parsing = _make_proxy("document_parsing", "src.nodes.preprocessing.document_parsing")
process_speech_to_text = _make_proxy("process_speech_to_text", "src.nodes.preprocessing.process_speech_to_text")
optimize_transcript = _make_proxy("optimize_transcript", "src.nodes.generation.optimize_transcript")
rag_processing = _make_proxy("rag_processing", "src.nodes.generation.rag_processing")
web_search = _make_proxy("web_search", "src.nodes.generation.web_search")
generate_response = _make_proxy("generate_response", "src.nodes.generation.generate_response")
behavior_detection = _make_proxy("behavior_detection", "src.nodes.generation.behavior_detection")
intent_recognition = _make_proxy("intent_recognition", "src.nodes.routing.intent_recognition")
agent_router = _make_proxy("agent_router", "src.nodes.routing.agent_router")
mock_interview = _make_proxy("mock_interview", "src.nodes.career_intents.mock_interview")
interview_review = _make_proxy("interview_review", "src.nodes.career_intents.interview_review")
career_planning = _make_proxy("career_planning", "src.nodes.career_intents.career_planning")


# ── Tool functions (langchain Tool contract: str → str JSON) ──────────────────

def pre_router_tool(input_str: str) -> str:
    """Route an input text to the right preprocessing path.

    Input: raw input text. Output: JSON of pre_route decision.
    """
    return _wrap_node_as_tool(pre_router, "input_text", "pre_route")(input_str)


def ocr_processing_tool(input_str: str) -> str:
    """Run OCR on a file path.

    Input: file path to an image/PDF. Output: JSON of OCR result.
    """
    return _wrap_node_as_tool(ocr_processing, "file_path", "ocr_result")(input_str)


def document_parsing_tool(input_str: str) -> str:
    """Parse a document file (PDF, DOCX, XLSX).

    Input: file path. Output: JSON of parsed_document.
    """
    return _wrap_node_as_tool(document_parsing, "file_path", "parsed_document")(input_str)


def process_speech_to_text_tool(input_str: str) -> str:
    """Transcribe audio to text.

    Input: audio file path. Output: JSON of transcript.
    """
    return _wrap_node_as_tool(process_speech_to_text, "audio_path", "transcript")(input_str)


def optimize_transcript_tool(input_str: str) -> str:
    """Optimize raw transcript for downstream processing (LLM polish).

    Input: raw transcript. Output: JSON of optimized_text.
    """
    return _wrap_node_as_tool(optimize_transcript, "transcript", "optimized_text")(input_str)


def rag_processing_tool(input_str: str) -> str:
    """Query the local RAG knowledge base.

    Input: query text. Output: JSON of rag_result + sources.
    """
    state = {"optimized_text": input_str, "input_text": input_str}
    try:
        out = rag_processing(state)
        result = {
            "rag_result": out.get("rag_result", ""),
            "rag_sources": out.get("rag_sources", []),
        }
    except Exception as e:
        result = {"success": False, "error": f"{type(e).__name__}: {e}"}
    return _json.dumps(result, ensure_ascii=False)


def web_search_tool(input_str: str) -> str:
    """Web search via MCP tavily tool.

    Input: search query. Output: JSON of web_search_result.
    """
    state = {"optimized_text": input_str, "input_text": input_str}
    try:
        out = web_search(state)
        result = {
            "web_search_result": out.get("web_search_result", ""),
            "web_sources": out.get("web_sources", []),
        }
    except Exception as e:
        result = {"success": False, "error": f"{type(e).__name__}: {e}"}
    return _json.dumps(result, ensure_ascii=False)


def generate_response_tool(input_str: str) -> str:
    """Generate the final response from context (RAG / web / behavior / direct).

    Input: context string. Output: JSON of response.
    """
    state = {"context": input_str, "input_text": input_str, "user_message": input_str}
    try:
        out = generate_response(state)
        result = {
            "response": out.get("response", ""),
            "history": out.get("history", []),
        }
    except Exception as e:
        result = {"success": False, "error": f"{type(e).__name__}: {e}"}
    return _json.dumps(result, ensure_ascii=False)


def behavior_detection_tool(input_str: str) -> str:
    """Run YOLO behavior analysis on a video frame (base64-encoded).

    Input: base64 video frame. Output: JSON of behavior_result.
    """
    return _wrap_node_as_tool(behavior_detection, "video_frame_data", "behavior_result")(input_str)


def intent_recognition_tool(input_str: str) -> str:
    """Classify user intent (mock_interview, interview_review, career_planning, normal_chat).

    Input: transcript. Output: JSON of intent (question_type, etc.).
    """
    state = {"transcript": input_str, "input_text": input_str}
    try:
        out = intent_recognition(state)
        result = out.get("intent", {"success": False, "error": "no intent field"})
    except Exception as e:
        result = {"success": False, "error": f"{type(e).__name__}: {e}"}
    return _json.dumps(result, ensure_ascii=False)


def agent_router_tool(input_str: str) -> str:
    """Decide which intent_mode to route to.

    Input: intent JSON string (will be re-parsed). Output: JSON of intent_mode.
    """
    try:
        parsed_intent = _json.loads(input_str) if input_str.strip() else {}
    except _json.JSONDecodeError:
        parsed_intent = {}
    state = {"intent": parsed_intent, "intent_mode": "normal_chat"}
    try:
        out = agent_router(state)
        result = {"intent_mode": out.get("intent_mode", "normal_chat")}
    except Exception as e:
        result = {"success": False, "error": f"{type(e).__name__}: {e}"}
    return _json.dumps(result, ensure_ascii=False)


def mock_interview_tool(input_str: str) -> str:
    """Run a mock interview round (LLM generates next question).

    Input: candidate transcript. Output: JSON of next question + history.
    """
    state = {"transcript": input_str, "input_text": input_str, "optimized_text": input_str}
    try:
        out = mock_interview(state)
        result = {
            "response": out.get("response", ""),
            "interview_history": out.get("interview_history", []),
            "history": out.get("history", []),
        }
    except Exception as e:
        result = {"success": False, "error": f"{type(e).__name__}: {e}"}
    return _json.dumps(result, ensure_ascii=False)


def interview_review_tool(input_str: str) -> str:
    """Generate a structured interview review report.

    Input: interview transcript/history. Output: JSON of review_report.
    """
    state = {"optimized_text": input_str, "input_text": input_str}
    try:
        out = interview_review(state)
        result = {
            "review_report": out.get("review_report", ""),
            "response": out.get("response", ""),
        }
    except Exception as e:
        result = {"success": False, "error": f"{type(e).__name__}: {e}"}
    return _json.dumps(result, ensure_ascii=False)


def career_planning_tool(input_str: str) -> str:
    """Generate a career plan based on user profile.

    Input: user profile / intent text. Output: JSON of career_plan.
    """
    state = {"optimized_text": input_str, "input_text": input_str}
    try:
        out = career_planning(state)
        result = {"career_plan": out.get("career_plan", "")}
    except Exception as e:
        result = {"success": False, "error": f"{type(e).__name__}: {e}"}
    return _json.dumps(result, ensure_ascii=False)


# ── Tool registry: name → callable ─────────────────────────────────────────────

TOOL_REGISTRY: dict = {
    "pre_router": pre_router_tool,
    "ocr_processing": ocr_processing_tool,
    "document_parsing": document_parsing_tool,
    "process_speech_to_text": process_speech_to_text_tool,
    "optimize_transcript": optimize_transcript_tool,
    "rag_processing": rag_processing_tool,
    "web_search": web_search_tool,
    "generate_response": generate_response_tool,
    "behavior_detection": behavior_detection_tool,
    "intent_recognition": intent_recognition_tool,
    "agent_router": agent_router_tool,
    "mock_interview": mock_interview_tool,
    "interview_review": interview_review_tool,
    "career_planning": career_planning_tool,
}
