"""Tests for AgenticRAGService — Think → Execute → Observe agent loop.

Covers:
- Fast path detection via FastPathHandler (greeting, chitchat, guidance)
- Agent loop with mock tools
- Max iterations limit
- Agent timeout handling
- Agent fallback on error
- Context accumulation and deduplication
- Token-based budgeting
- Different evidence states
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

from backend.services.agent.service import (
    AgentResult,
    AgenticRAGService,
    _VALID_TOOLS,
    _VALID_EVIDENCE_STATES,
    _MAX_ITERATIONS_DEFAULT,
    _ITERATION_TIMEOUT_SECONDS,
    _TOTAL_TIMEOUT_SECONDS,
)
from backend.services.agent.service import _search_event_message
from backend.services.agent.fast_path import FastPathResponse
from backend.services.retrieval.models import RetrievedChunk
from backend.models.meeting_models import MeetingChunkRecord


def _make_chunk(
    chunk_id: str = "chunk-001",
    meeting_id: str = "meeting-001",
    text: str = "Sample chunk text",
    section_type: str = "summary.executive",
    source_type: str = "transcript",
    score: float = 0.9,
) -> RetrievedChunk:
    """Create a RetrievedChunk for testing."""
    record = MagicMock(spec=MeetingChunkRecord)
    record.chunk_id = chunk_id
    record.meeting_id = meeting_id
    record.text = text
    record.section_type = section_type
    record.source_type = source_type
    record.citation_ids = [f"cite-{chunk_id}"]
    record.segment_ids = [f"seg-{chunk_id}"]
    record.start_ms = 0
    record.end_ms = 1000
    record.metadata_json = {"title": "Test"}
    record.json_pointer = f"/chunks/{chunk_id}"
    return RetrievedChunk(record=record, score=score)


class FakeLLMProvider:
    """Fake LLM provider for testing."""

    provider_name = "fake-llm"
    model_name = "fake-model"

    def __init__(self, responses: list[dict] | None = None) -> None:
        self.responses = responses or []
        self.call_count = 0

    def generate_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0) -> dict:
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        return {
            "action": "synthesize",
            "reasoning": "No more responses configured",
            "answer": "Default answer",
            "evidenceState": "grounded",
            "confidence": 0.8,
        }


class FakeRetrievalSearch:
    """Fake retrieval search service for testing."""

    def __init__(self, chunks: list[RetrievedChunk] | None = None) -> None:
        self.chunks = chunks or []
        self.search_calls: list[dict] = []

    def search_meeting(
        self,
        *,
        meeting_id: str,
        query: str,
        limit: int = 5,
    ) -> list[RetrievedChunk]:
        self.search_calls.append({
            "meeting_id": meeting_id,
            "query": query,
            "limit": limit,
        })
        return self.chunks[:limit]


class AgenticRAGServiceTestCase(unittest.TestCase):
    """Test cases for AgenticRAGService."""

    def setUp(self) -> None:
        self.session = MagicMock()
        self.meeting_id = "test-meeting-001"

    def test_fast_path_greeting(self) -> None:
        """Test fast path detection for greetings via FastPathHandler."""
        llm = FakeLLMProvider([{"needsRag": False, "answer": "Hello! How can I help?"}])
        service = AgenticRAGService(
            session=self.session,
            llm_provider=llm,
        )
        result = service.fast_path_handler.handle("Hello")
        self.assertIsNotNone(result)
        self.assertEqual(result.answer, "Hello! How can I help?")
        self.assertEqual(result.evidence_state, "fast_path")

    def test_fast_path_small_talk(self) -> None:
        """Test fast path detection for small talk via FastPathHandler."""
        llm = FakeLLMProvider([{"needsRag": False, "answer": "I'm doing well!"}])
        service = AgenticRAGService(
            session=self.session,
            llm_provider=llm,
        )
        result = service.fast_path_handler.handle("How are you?")
        self.assertIsNotNone(result)
        self.assertIn("well", result.answer)

    def test_fast_path_capability(self) -> None:
        """Test fast path detection for capability questions via FastPathHandler."""
        llm = FakeLLMProvider([{"needsRag": False, "answer": "I can help with meeting analysis."}])
        service = AgenticRAGService(
            session=self.session,
            llm_provider=llm,
        )
        result = service.fast_path_handler.handle("What can you do?")
        self.assertIsNotNone(result)
        self.assertIn("meeting", result.answer)

    def test_fast_path_returns_none_for_meeting_question(self) -> None:
        """Test that meeting questions are not detected as fast path."""
        llm = FakeLLMProvider([{"needsRag": True}])
        service = AgenticRAGService(
            session=self.session,
            llm_provider=llm,
        )
        result = service.fast_path_handler.handle("What decisions were made in the meeting?")
        self.assertIsNone(result)

    def test_fast_path_generate_answer(self) -> None:
        """Test that generate_answer returns fast path result for greetings."""
        llm = FakeLLMProvider([{"needsRag": False, "answer": "Hello! How can I help?"}])
        service = AgenticRAGService(
            session=self.session,
            llm_provider=llm,
        )
        result = service.generate_answer(
            meeting_id=self.meeting_id,
            question="Hello",
        )
        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.evidence_state, "fast_path")
        self.assertEqual(result.provider, "agentic-rag-fast-path")

    def test_agent_loop_basic_flow(self) -> None:
        """Test basic agent loop flow with Think → Execute → Observe."""
        chunk = _make_chunk()
        retrieval = FakeRetrievalSearch(chunks=[chunk])
        llm = FakeLLMProvider(responses=[
            {
                "action": "continue",
                "reasoning": "Need more information",
                "tool_calls": [{"tool": "search_semantic", "parameters": {"query": "decisions"}}],
            },
            {
                "action": "synthesize",
                "reasoning": "Have enough context",
                "answer": "The meeting discussed decisions.",
                "evidenceState": "grounded",
                "confidence": 0.9,
            },
        ])

        service = AgenticRAGService(
            session=self.session,
            llm_provider=llm,
            retrieval_search=retrieval,
        )

        with patch.object(service, '_execute_tools') as mock_execute:
            mock_execute.return_value = MagicMock(
                tool_results=[MagicMock(
                    succeeded=True,
                    has_results=True,
                    result=[{
                        "chunkId": "chunk-001",
                        "meetingId": "meeting-001",
                        "text": "Sample text",
                        "sourceType": "transcript",
                        "sectionType": "summary.executive",
                        "jsonPointer": "/chunks/chunk-001",
                        "citationIds": [],
                        "segmentIds": [],
                        "startMs": 0,
                        "endMs": 1000,
                        "metadata": {},
                        "score": 0.9,
                    }],
                )],
                success_count=1,
                failure_count=0,
                total_duration_ms=100,
            )
            result = service.generate_answer(
                question="What decisions were made?",
                meeting_id=self.meeting_id,
            )

        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.evidence_state, "grounded")
        self.assertGreater(result.iterations, 0)

    def test_max_iterations_limit(self) -> None:
        """Test that agent loop respects max iterations limit."""
        chunk = _make_chunk()
        retrieval = FakeRetrievalSearch(chunks=[chunk])
        # Always return "continue" to force max iterations
        llm = FakeLLMProvider(responses=[
            {
                "action": "continue",
                "reasoning": "Need more",
                "tool_calls": [{"tool": "search_semantic", "parameters": {"query": "test"}}],
            }
        ] * 10)

        service = AgenticRAGService(
            session=self.session,
            llm_provider=llm,
            retrieval_search=retrieval,
            max_iterations=2,
        )

        with patch.object(service, '_execute_tools') as mock_execute:
            mock_execute.return_value = MagicMock(
                tool_results=[],
                success_count=0,
                failure_count=0,
                total_duration_ms=0,
            )
            result = service.generate_answer(
                question="Test question",
                meeting_id=self.meeting_id,
            )

        # Should have stopped at max_iterations
        self.assertLessEqual(result.iterations, 2)

    def test_agent_timeout_handling(self) -> None:
        """Test that agent loop handles timeout gracefully."""
        def slow_think(*args, **kwargs):
            time.sleep(0.1)
            return {
                "action": "continue",
                "reasoning": "Slow",
                "tool_calls": [],
            }

        service = AgenticRAGService(
            session=self.session,
            llm_provider=FakeLLMProvider(),
            retrieval_search=FakeRetrievalSearch(),
            total_timeout_seconds=0.05,  # Very short timeout
        )

        with patch.object(service, '_think', side_effect=slow_think):
            result = service.generate_answer(
                question="Test timeout",
                meeting_id=self.meeting_id,
            )

        # Should complete without hanging
        self.assertIsInstance(result, AgentResult)

    def test_agent_fallback_on_llm_error(self) -> None:
        """Test fallback behavior when LLM provider raises error."""
        from backend.providers.llm import LLMProviderError

        class ErrorLLMProvider:
            provider_name = "error-llm"
            model_name = "error-model"

            def generate_json(self, **kwargs):
                raise LLMProviderError("LLM unavailable")

        chunk = _make_chunk(text="Fallback content")
        retrieval = FakeRetrievalSearch(chunks=[chunk])

        service = AgenticRAGService(
            session=self.session,
            llm_provider=ErrorLLMProvider(),
            retrieval_search=retrieval,
        )

        result = service.generate_answer(
            question="Test fallback",
            meeting_id=self.meeting_id,
        )

        # Should return fallback result
        self.assertIsInstance(result, AgentResult)
        self.assertIn("Fallback content", result.answer)

    def test_context_accumulation_and_deduplication(self) -> None:
        """Test that chunks are accumulated and deduplicated across iterations."""
        chunk1 = _make_chunk(chunk_id="chunk-001", text="First chunk")
        chunk2 = _make_chunk(chunk_id="chunk-002", text="Second chunk")
        chunk1_dup = _make_chunk(chunk_id="chunk-001", text="First chunk duplicate")

        retrieval = FakeRetrievalSearch(chunks=[chunk1, chunk2, chunk1_dup])
        llm = FakeLLMProvider(responses=[
            {
                "action": "continue",
                "reasoning": "Need more",
                "tool_calls": [{"tool": "search_semantic", "parameters": {"query": "test"}}],
            },
            {
                "action": "synthesize",
                "reasoning": "Enough",
                "answer": "Combined answer",
                "evidenceState": "grounded",
                "confidence": 0.85,
            },
        ])

        service = AgenticRAGService(
            session=self.session,
            llm_provider=llm,
            retrieval_search=retrieval,
        )

        with patch.object(service, '_execute_tools') as mock_execute:
            mock_execute.return_value = MagicMock(
                tool_results=[MagicMock(
                    succeeded=True,
                    has_results=True,
                    result=[
                        {
                            "chunkId": "chunk-001",
                            "text": "First chunk",
                            "sourceType": "transcript",
                            "sectionType": "summary.executive",
                            "meetingId": "meeting-001",
                            "jsonPointer": "/chunks/001",
                            "citationIds": [],
                            "segmentIds": [],
                            "metadata": {},
                            "score": 0.9,
                        },
                        {
                            "chunkId": "chunk-002",
                            "text": "Second chunk",
                            "sourceType": "transcript",
                            "sectionType": "summary.executive",
                            "meetingId": "meeting-001",
                            "jsonPointer": "/chunks/002",
                            "citationIds": [],
                            "segmentIds": [],
                            "metadata": {},
                            "score": 0.8,
                        },
                    ],
                )],
                success_count=1,
                failure_count=0,
                total_duration_ms=100,
            )
            result = service.generate_answer(
                question="Test dedup",
                meeting_id=self.meeting_id,
            )

        self.assertIsInstance(result, AgentResult)

    def test_token_budget_stops_accumulation(self) -> None:
        """Test that token budget limits chunk accumulation."""
        service = AgenticRAGService(
            session=self.session,
            llm_provider=FakeLLMProvider(),
        )
        # Set a very small token budget
        service.token_manager = MagicMock()
        service.token_manager.count_tokens.return_value = 5000
        service.token_manager.create_budget.return_value = MagicMock(
            total_limit=100,
            is_exhausted=True,
        )

        execution = MagicMock()
        execution.tool_results = [MagicMock(
            succeeded=True,
            has_results=True,
            result=[{"chunkId": "c1", "text": "test"}],
        )]
        execution.success_count = 1
        execution.failure_count = 0

        added, tokens = service._accumulate_context(
            execution=execution,
            accumulated_context=[],
            seen_chunk_ids=set(),
            accumulated_tokens=0,
            token_budget=MagicMock(is_exhausted=True),
        )
        self.assertEqual(added, 0)

    def test_evidence_state_grounded(self) -> None:
        """Test grounded evidence state."""
        result = AgentResult(
            answer="Test answer",
            evidence_state="grounded",
            confidence=0.95,
        )
        self.assertEqual(result.evidence_state, "grounded")
        self.assertIn("grounded", _VALID_EVIDENCE_STATES)

    def test_evidence_state_partial(self) -> None:
        """Test partial evidence state."""
        result = AgentResult(
            answer="Partial answer",
            evidence_state="partial",
            confidence=0.5,
        )
        self.assertEqual(result.evidence_state, "partial")
        self.assertIn("partial", _VALID_EVIDENCE_STATES)

    def test_evidence_state_not_enough(self) -> None:
        """Test not_enough_evidence state."""
        result = AgentResult(
            answer="Not enough",
            evidence_state="not_enough_evidence",
            confidence=0.2,
        )
        self.assertEqual(result.evidence_state, "not_enough_evidence")

    def test_evidence_state_fast_path(self) -> None:
        """Test fast_path evidence state."""
        result = AgentResult(
            answer="Hello!",
            evidence_state="fast_path",
            confidence=0.9,
        )
        self.assertEqual(result.evidence_state, "fast_path")

    def test_valid_tools_set(self) -> None:
        """Test that valid tools set contains expected tools."""
        expected_tools = {
            "search_semantic",
            "search_keyword",
            "search_records",
            "search_section",
            "get_summary",
        }
        self.assertEqual(_VALID_TOOLS, expected_tools)

    def test_nationality_question_adds_semantic_fact_search_when_agent_selects_participants(self) -> None:
        service = AgenticRAGService(
            session=self.session,
            llm_provider=FakeLLMProvider(),
        )

        calls = service._valid_tool_calls(
            [{"tool": "search_records", "parameters": {"record_types": ["participant"]}}],
            question="Những người tham gia cuộc họp có quốc tịch là gì?",
        )

        self.assertEqual(calls[0]["tool"], "search_semantic")
        self.assertEqual(calls[0]["parameters"]["query"], "Những người tham gia cuộc họp có quốc tịch là gì?")
        self.assertEqual(calls[0]["parameters"]["limit"], 6)
        self.assertEqual(calls[1]["tool"], "search_records")

    def test_search_event_message_uses_natural_vietnamese_tool_copy(self) -> None:
        message = _search_event_message([
            {"tool": "search_semantic", "parameters": {"query": "người tham gia"}},
            {"tool": "get_participants", "parameters": {}},
        ])

        self.assertEqual(message, "Đang tìm bằng chứng trong cuộc họp...")
        self.assertNotIn("Đang tìm bằng tìm kiếm ngữ nghĩa", message)

    def test_agent_result_to_payload(self) -> None:
        """Test AgentResult serialization to payload."""
        result = AgentResult(
            answer="Test",
            evidence_state="grounded",
            confidence=0.9,
            iterations=2,
            tool_calls_summary=[{"tool": "search_semantic"}],
            agent_thoughts=[{"iteration": 1, "decision": "continue"}],
        )
        payload = result.to_answer_payload()
        self.assertEqual(payload["answer"], "Test")
        self.assertEqual(payload["evidenceState"], "grounded")
        self.assertEqual(payload["confidence"], 0.9)
        self.assertEqual(payload["agentIterations"], 2)
        self.assertIn("agentToolCalls", payload)
        self.assertIn("agentThoughts", payload)

    def test_tool_registry_integration(self) -> None:
        """Test that service uses AgentToolRegistry for tool execution."""
        from backend.services.agent.tool_registry import AgentToolRegistry

        service = AgenticRAGService(
            session=self.session,
            llm_provider=FakeLLMProvider(),
        )
        self.assertIsInstance(service.tool_registry, AgentToolRegistry)

    def test_token_manager_integration(self) -> None:
        """Test that service uses TokenManager for context budgeting."""
        from backend.services.agent.token_management import TokenManager

        service = AgenticRAGService(
            session=self.session,
            llm_provider=FakeLLMProvider(),
        )
        self.assertIsInstance(service.token_manager, TokenManager)

    def test_fast_path_handler_integration(self) -> None:
        """Test that service uses FastPathHandler for fast path detection."""
        from backend.services.agent.fast_path import FastPathHandler

        service = AgenticRAGService(
            session=self.session,
            llm_provider=FakeLLMProvider(),
        )
        self.assertIsInstance(service.fast_path_handler, FastPathHandler)

    def test_new_progress_events_are_emitted_in_order(self) -> None:
        llm = FakeLLMProvider(responses=[
            {"action": "continue", "tool_calls": [{"tool": "search_semantic", "parameters": {"query": "summary"}}]},
            {"action": "continue", "tool_calls": [{"tool": "search_semantic", "parameters": {"query": "summary"}}]},
        ])
        service = AgenticRAGService(session=self.session, llm_provider=llm, retrieval_search=FakeRetrievalSearch())
        events: list[dict] = []
        with patch.object(service, "_execute_tools") as execute:
            execute.return_value = MagicMock(
                tool_results=[], success_count=0, failure_count=0, total_duration_ms=0
            )
            service.generate_answer(meeting_id=self.meeting_id, question="Tóm tắt cuộc họp", event_callback=events.append)

        event_types = [event["type"] for event in events]
        self.assertIn("agent_plan", event_types)
        self.assertIn("agent_verify", event_types)
        self.assertIn("agent_synthesize", event_types)
        self.assertLess(event_types.index("agent_plan"), event_types.index("agent_verify"))


if __name__ == "__main__":
    unittest.main()
