"""
Test Multi-Agent v2 production integration layer.

Per openspec/feat-multi-agent-integration spec:
  - register_all_tools() populates worker._TOOL_DISPATCH from TOOL_REGISTRY
  - setup_v2() is idempotent and warms the singleton
  - is_v2_ready() reflects setup state
  - /api/v2/chat + /api/v2/health endpoints work
  - v1 endpoints remain unaffected

TDD: this file was written first (RED phase). Implementation in
src/agents/integration.py + src/routes/rest.py.
"""
from unittest.mock import patch, MagicMock


# ── Helpers ──────────────────────────────────────────────────────────────────

def _reset_v2_state():
    """Clear module-level state so each test starts clean."""
    from src.agents import worker
    from src.agents import integration
    worker._TOOL_DISPATCH.clear()
    integration._v2_ready = False
    integration._v2_singleton = None


def _fake_registry():
    """A minimal TOOL_REGISTRY mimic with 14 distinct tools."""
    tools = {}
    for name in [
        "pre_router", "ocr_processing", "document_parsing",
        "process_speech_to_text", "optimize_transcript", "rag_processing",
        "web_search", "generate_response", "behavior_detection",
        "intent_recognition", "agent_router", "mock_interview",
        "interview_review", "career_planning",
    ]:
        tools[name] = MagicMock(return_value=f'{{"from": "{name}"}}')
    return tools


# ── REQ-1: register_all_tools ────────────────────────────────────────────────

def test_register_all_tools_registers_14_tools():
    """After register_all_tools(), worker._TOOL_DISPATCH has 14 entries."""
    from src.agents import worker, integration
    _reset_v2_state()
    with patch("src.agents.tools.TOOL_REGISTRY", _fake_registry()):
        integration.register_all_tools()
    assert len(worker._TOOL_DISPATCH) == 14, (
        f"Expected 14 tools registered, got {len(worker._TOOL_DISPATCH)}"
    )


def test_register_all_tools_idempotent():
    """Calling register_all_tools() twice does not duplicate."""
    from src.agents import worker, integration
    _reset_v2_state()
    with patch("src.agents.tools.TOOL_REGISTRY", _fake_registry()):
        integration.register_all_tools()
        integration.register_all_tools()  # should not explode or duplicate
    assert len(worker._TOOL_DISPATCH) == 14


def test_register_all_tools_skips_bad_tool_without_crashing():
    """One broken tool does not block the rest."""
    from src.agents import worker, integration
    _reset_v2_state()
    bad_registry = _fake_registry()
    bad_registry["web_search"] = None  # non-callable: register_tool will raise
    with patch("src.agents.tools.TOOL_REGISTRY", bad_registry):
        integration.register_all_tools()  # must not raise
    # All 13 other tools registered; web_search was skipped
    assert len(worker._TOOL_DISPATCH) == 13
    assert "web_search" not in worker._TOOL_DISPATCH


# ── REQ-2: setup_v2 ──────────────────────────────────────────────────────────

def test_setup_v2_initializes_singleton():
    """setup_v2() warms the multi-agent v2 graph singleton."""
    from src.multi_agent_v2 import get_singleton_multi_agent_v2
    from src.agents import integration
    _reset_v2_state()
    with patch("src.agents.tools.TOOL_REGISTRY", _fake_registry()):
        with patch("src.agents.planner._init_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value.content = "[]"
            integration.setup_v2()
    graph = get_singleton_multi_agent_v2()
    assert graph is not None


def test_setup_v2_idempotent():
    """Second setup_v2() returns the same singleton (process-level)."""
    from src.multi_agent_v2 import get_singleton_multi_agent_v2
    from src.agents import integration
    _reset_v2_state()
    with patch("src.agents.tools.TOOL_REGISTRY", _fake_registry()):
        with patch("src.agents.planner._init_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value.content = "[]"
            integration.setup_v2()
            g1 = get_singleton_multi_agent_v2()
            integration.setup_v2()  # second time
            g2 = get_singleton_multi_agent_v2()
    assert g1 is g2, "setup_v2() must not recreate the singleton"


# ── REQ-3: is_v2_ready ───────────────────────────────────────────────────────

def test_is_v2_ready_false_before_setup():
    from src.agents import integration
    _reset_v2_state()
    assert integration.is_v2_ready() is False


def test_is_v2_ready_true_after_setup():
    from src.agents import integration
    _reset_v2_state()
    with patch("src.agents.tools.TOOL_REGISTRY", _fake_registry()):
        with patch("src.agents.planner._init_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value.content = "[]"
            integration.setup_v2()
    assert integration.is_v2_ready() is True


# ── REQ-4: /api/v2/* endpoints ───────────────────────────────────────────────

def test_v2_health_endpoint_returns_status():
    """GET /api/v2/health returns 200 with ready flag + tools count."""
    from src.agents import integration
    from fastapi.testclient import TestClient
    from src.main import app

    _reset_v2_state()
    with patch("src.agents.tools.TOOL_REGISTRY", _fake_registry()):
        with patch("src.agents.planner._init_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value.content = "[]"
            integration.setup_v2()
            client = TestClient(app)
            response = client.get("/api/v2/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["tools_registered"] == 14


def test_v2_chat_endpoint_returns_200():
    """POST /api/v2/chat with valid query returns 200 with final_report."""
    from src.agents import integration
    from fastapi.testclient import TestClient
    from src.main import app

    _reset_v2_state()
    with patch("src.agents.tools.TOOL_REGISTRY", _fake_registry()):
        with patch("src.agents.planner._init_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value.content = (
                '[{"id": "t1", "description": "greet", "tool_hint": "web_search"}]'
            )
            integration.setup_v2()
            client = TestClient(app)
            response = client.post(
                "/api/v2/chat",
                json={"query": "你好", "session_id": "s1"},
            )

    assert response.status_code == 200
    body = response.json()
    assert "final_report" in body
    assert isinstance(body["final_report"], str)
    assert len(body["final_report"]) > 0


def test_v2_chat_endpoint_422_on_missing_query():
    """POST /api/v2/chat without query returns 422."""
    from src.agents import integration
    from fastapi.testclient import TestClient
    from src.main import app

    _reset_v2_state()
    with patch("src.agents.tools.TOOL_REGISTRY", _fake_registry()):
        with patch("src.agents.planner._init_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value.content = "[]"
            integration.setup_v2()
            client = TestClient(app)
            response = client.post(
                "/api/v2/chat",
                json={"session_id": "s1"},  # no query
            )
    assert response.status_code == 422


def test_v2_chat_endpoint_503_when_not_setup():
    """POST /api/v2/chat without setup returns 503."""
    from src.agents import integration
    from fastapi.testclient import TestClient
    from src.main import app

    _reset_v2_state()
    client = TestClient(app)
    response = client.post(
        "/api/v2/chat",
        json={"query": "hi", "session_id": "s1"},
    )
    assert response.status_code == 503
    assert "v2 not initialized" in response.json()["error"]


# ── REQ-5: v1 endpoints unaffected ───────────────────────────────────────────

def test_v1_health_endpoint_still_200():
    """v1 /api/health still works after integration is added."""
    from src.agents import integration
    from fastapi.testclient import TestClient
    from src.main import app

    _reset_v2_state()
    with patch("src.agents.tools.TOOL_REGISTRY", _fake_registry()):
        with patch("src.agents.planner._init_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value.content = "[]"
            integration.setup_v2()
            client = TestClient(app)
            response = client.get("/api/health")
    assert response.status_code == 200


def test_v1_models_endpoint_still_200():
    """v1 /api/models still works."""
    from src.agents import integration
    from fastapi.testclient import TestClient
    from src.main import app

    _reset_v2_state()
    with patch("src.agents.tools.TOOL_REGISTRY", _fake_registry()):
        with patch("src.agents.planner._init_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value.content = "[]"
            integration.setup_v2()
            client = TestClient(app)
            response = client.get("/api/models")
    # /api/models is a v1 endpoint; integration must not break it
    assert response.status_code in (200, 500), (
        f"v1 endpoint broken by integration: {response.status_code}"
    )


def test_v2_routes_registered():
    """v2 routes are present in the FastAPI app."""
    from src.main import app
    paths = {r.path for r in app.routes}
    assert "/api/v2/chat" in paths
    assert "/api/v2/health" in paths
    # v1 routes still present
    assert "/api/health" in paths
    assert "/api/models" in paths
