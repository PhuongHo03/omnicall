"""Tests for FastPathHandler — LLM-based fast path detection.

Covers:
- LLM returns needsRag=false → FastPathResponse
- LLM returns needsRag=true → None
- LLM error → falls through to RAG
- Empty/invalid answer → None
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from backend.providers.llm import LLMProviderError
from backend.services.agent.fast_path import (
    FastPathHandler,
    FastPathResponse,
)


class FakeLLM:
    """Fake LLM that returns preconfigured responses."""

    def __init__(self, response: dict | None = None, *, raise_error: bool = False) -> None:
        self._response = response or {}
        self._raise = raise_error
        self.calls: list[dict] = []

    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0) -> dict:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": temperature,
            }
        )
        if self._raise:
            raise LLMProviderError("LLM unavailable")
        return self._response


class FastPathHandlerTestCase(unittest.TestCase):
    """Test cases for FastPathHandler."""

    # ------------------------------------------------------------------
    # handle() — needsRag=false
    # ------------------------------------------------------------------

    def test_handle_returns_response_when_needs_rag_false(self) -> None:
        """Test that handle returns FastPathResponse when LLM says needsRag=false."""
        llm = FakeLLM({"needsRag": False, "answer": "Hello! How can I help?"})
        handler = FastPathHandler(llm)
        result = handler.handle("hi")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, FastPathResponse)
        self.assertEqual(result.answer, "Hello! How can I help?")
        self.assertEqual(result.evidence_state, "fast_path")

    def test_handle_strips_whitespace_from_answer(self) -> None:
        """Test that answer whitespace is stripped."""
        llm = FakeLLM({"needsRag": False, "answer": "  Hello!  "})
        handler = FastPathHandler(llm)
        result = handler.handle("hi")
        self.assertIsNotNone(result)
        self.assertEqual(result.answer, "Hello!")

    def test_handle_vietnamese_greeting(self) -> None:
        """Test Vietnamese greeting handled by LLM."""
        llm = FakeLLM({"needsRag": False, "answer": "Xin chào! Mình có thể giúp gì?"})
        handler = FastPathHandler(llm)
        result = handler.handle("xin chào")
        self.assertIsNotNone(result)
        self.assertIn("Xin chào", result.answer)

    def test_handle_uses_fast_path_temperature(self) -> None:
        """Test fast path uses a higher temperature than deterministic JSON flows."""
        llm = FakeLLM({"needsRag": False, "answer": "Xin chào! Rất vui được gặp bạn."})
        handler = FastPathHandler(llm)

        result = handler.handle("xin chào")

        self.assertIsNotNone(result)
        self.assertEqual(llm.calls[0]["temperature"], 0.5)

    # ------------------------------------------------------------------
    # handle() — needsRag=true
    # ------------------------------------------------------------------

    def test_handle_returns_none_when_needs_rag_true(self) -> None:
        """Test that handle returns None when LLM says needsRag=true."""
        llm = FakeLLM({"needsRag": True})
        handler = FastPathHandler(llm)
        result = handler.handle("What decisions were made?")
        self.assertIsNone(result)

    def test_handle_returns_none_when_needs_rag_missing(self) -> None:
        """Test that handle returns None when needsRag key is missing."""
        llm = FakeLLM({"answer": "some answer"})
        handler = FastPathHandler(llm)
        result = handler.handle("What decisions were made?")
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # handle() — error handling
    # ------------------------------------------------------------------

    def test_handle_returns_none_on_llm_error(self) -> None:
        """Test that handle returns None when LLM raises error."""
        llm = FakeLLM(raise_error=True)
        handler = FastPathHandler(llm)
        result = handler.handle("hello")
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # handle() — invalid answer
    # ------------------------------------------------------------------

    def test_handle_returns_none_for_empty_answer(self) -> None:
        """Test that handle returns None when answer is empty."""
        llm = FakeLLM({"needsRag": False, "answer": ""})
        handler = FastPathHandler(llm)
        result = handler.handle("hi")
        self.assertIsNone(result)

    def test_handle_returns_none_for_whitespace_only_answer(self) -> None:
        """Test that handle returns None when answer is whitespace only."""
        llm = FakeLLM({"needsRag": False, "answer": "   "})
        handler = FastPathHandler(llm)
        result = handler.handle("hi")
        self.assertIsNone(result)

    def test_handle_returns_none_for_non_string_answer(self) -> None:
        """Test that handle returns None when answer is not a string."""
        llm = FakeLLM({"needsRag": False, "answer": 123})
        handler = FastPathHandler(llm)
        result = handler.handle("hi")
        self.assertIsNone(result)

    def test_handle_returns_none_when_answer_missing(self) -> None:
        """Test that handle returns None when answer key is missing."""
        llm = FakeLLM({"needsRag": False})
        handler = FastPathHandler(llm)
        result = handler.handle("hi")
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # Various question types
    # ------------------------------------------------------------------

    def test_handle_greeting(self) -> None:
        """Test greeting detected as fast path."""
        llm = FakeLLM({"needsRag": False, "answer": "Hey there!"})
        handler = FastPathHandler(llm)
        self.assertIsNotNone(handler.handle("hello"))

    def test_handle_farewell(self) -> None:
        """Test farewell detected as fast path."""
        llm = FakeLLM({"needsRag": False, "answer": "Goodbye!"})
        handler = FastPathHandler(llm)
        self.assertIsNotNone(handler.handle("bye"))

    def test_handle_small_talk(self) -> None:
        """Test small talk detected as fast path."""
        llm = FakeLLM({"needsRag": False, "answer": "I'm doing well!"})
        handler = FastPathHandler(llm)
        self.assertIsNotNone(handler.handle("how are you"))

    def test_handle_meeting_question_goes_to_rag(self) -> None:
        """Test meeting question not caught by fast path."""
        llm = FakeLLM({"needsRag": True})
        handler = FastPathHandler(llm)
        self.assertIsNone(handler.handle("What action items were assigned?"))


if __name__ == "__main__":
    unittest.main()
