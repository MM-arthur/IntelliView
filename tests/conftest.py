"""
Pytest fixtures for IntelliView multi-agent tests.

Mocks the LLM factory (`init_llm`) so we test graph behavior,
not LLM internal mechanics. TDD rule: test behavior, not implementation.
"""
import os
import sys
from typing import Any
from unittest.mock import MagicMock

import pytest

# Ensure src/ is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class FakeLLMResponse:
    """Mimics langchain AIMessage with .content + structured output support."""

    def __init__(self, content: str = "", **kwargs):
        self.content = content
        self.additional_kwargs = kwargs
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeLLM:
    """Fake LLM that returns scripted responses in order.

    Usage:
        fake = FakeLLM()
        fake.queue_response(FakeLLMResponse(content='{"tasks": [...]}'))
        fake.queue_response(FakeLLMResponse(content='{"result": "..."}'))
    """

    def __init__(self):
        self._responses: list[Any] = []
        self._call_count = 0
        self._calls: list[dict] = []

    def queue_response(self, response):
        self._responses.append(response)

    def invoke(self, *args, **kwargs):
        self._call_count += 1
        self._calls.append({"args": args, "kwargs": kwargs})
        if not self._responses:
            raise RuntimeError(
                f"FakeLLM exhausted at call #{self._call_count} - "
                "did you forget to queue_response()?"
            )
        return self._responses.pop(0)

    # For langchain tool-calling style: with_structured_output
    def with_structured_output(self, schema):
        mock = MagicMock()
        mock.invoke = self.invoke
        return mock

    # For bind_tools style
    def bind_tools(self, tools):
        mock = MagicMock()
        mock.invoke = self.invoke
        return mock


@pytest.fixture
def fake_llm():
    """A fresh FakeLLM for each test."""
    return FakeLLM()


@pytest.fixture
def patched_init_llm(monkeypatch, fake_llm):
    """Patch src.core.llm_factory.init_llm to return our FakeLLM."""
    try:
        from src.core.llm_factory import init_llm

        monkeypatch.setattr("src.core.llm_factory.init_llm", lambda *a, **kw: fake_llm)
    except (ImportError, ModuleNotFoundError):
        # Factory not yet implemented - tests should still structure around it
        pass
    return fake_llm
