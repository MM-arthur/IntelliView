"""
Test Tool wrappers for original 15 nodes.

Spec: openspec/changes/feat-multi-agent/specs/multi-agent/spec.md
      REQ-001 "原 node 改 Tool 后行为必须等价"

Phase: 1-Worker demo (Task 2.a: convert behavior_detection to Tool)

TDD rule: test the Tool wrapper is behavior-equivalent to the original node.
"""
import json
from unittest.mock import patch, MagicMock

from src.agents.tools import behavior_detection_tool


def test_behavior_detection_tool_returns_json():
    """Tool output is JSON-serializable (langchain Tool contract)."""
    fake_node = MagicMock()
    fake_node.__name__ = "behavior_detection"  # required by _wrap_node_as_tool
    fake_node.return_value = {"behavior_result": {"success": True, "behavior": "smiling", "confidence": 0.95}}
    with patch("src.agents.tools.behavior_detection", fake_node):
        out = behavior_detection_tool("base64_video_data_here")

    parsed = json.loads(out)
    assert parsed["success"] is True
    assert parsed["behavior"] == "smiling"


def test_behavior_detection_tool_handles_node_error():
    """If node raises, Tool returns error JSON, not exception."""
    fake_node = MagicMock()
    fake_node.__name__ = "behavior_detection"
    fake_node.side_effect = RuntimeError("YOLO model not loaded")
    with patch("src.agents.tools.behavior_detection", fake_node):
        out = behavior_detection_tool("base64_data")

    parsed = json.loads(out)
    assert parsed["success"] is False
    assert "YOLO" in parsed["error"] or "RuntimeError" in parsed["error"]


def test_behavior_detection_tool_behavior_equivalent_to_node():
    """Tool wrapper must produce same behavior_result as the original node.

    Critical regression test per task table #4 risk section.
    """
    fake_node = MagicMock()
    fake_node.__name__ = "behavior_detection"
    fake_node.return_value = {
        "video_frame_data": "base64_data",
        "behavior_result": {"success": True, "score": 0.88},
        "some_other_field": "preserved",
    }
    with patch("src.agents.tools.behavior_detection", fake_node):
        out = behavior_detection_tool("base64_data")

    parsed = json.loads(out)
    assert parsed == {"success": True, "score": 0.88}
    assert "some_other_field" not in parsed


def test_behavior_detection_tool_empty_input():
    """Empty input: Tool returns error JSON, not crash."""
    fake_node = MagicMock()
    fake_node.__name__ = "behavior_detection"
    fake_node.return_value = {
        "behavior_result": {"success": False, "error": "No video frame data"}
    }
    with patch("src.agents.tools.behavior_detection", fake_node):
        out = behavior_detection_tool("")

    parsed = json.loads(out)
    assert parsed["success"] is False
    assert "No video" in parsed["error"]
