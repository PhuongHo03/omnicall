"""Tests for AgentContextManager — Context accumulation and management.

Covers:
- Test chunk deduplication
- Test max chunks limits
- Test context formatting
- Test citation extraction
"""

from __future__ import annotations

import unittest

from backend.services.agent.context_manager import (
    AgentContext,
    AgentContextManager,
    ContextChunk,
    ToolCallRecord,
    get_agent_context_manager,
)


def _make_context_chunk(
    chunk_id: str = "chunk-001",
    text: str = "Sample text",
    score: float = 0.9,
    source_type: str = "transcript",
    section_type: str = "summary.executive",
    citation_ids: list[str] | None = None,
    segment_ids: list[str] | None = None,
) -> ContextChunk:
    """Create a ContextChunk for testing."""
    return ContextChunk(
        chunk_id=chunk_id,
        text=text,
        score=score,
        source_type=source_type,
        section_type=section_type,
        citation_ids=citation_ids or [f"cite-{chunk_id}"],
        segment_ids=segment_ids or [f"seg-{chunk_id}"],
    )


class AgentContextManagerTestCase(unittest.TestCase):
    """Test cases for AgentContextManager."""

    def setUp(self) -> None:
        self.manager = AgentContextManager(
            max_chunks_per_tool=3,
            max_total_chunks=5,
        )

    # ------------------------------------------------------------------
    # Basic initialization tests
    # ------------------------------------------------------------------

    def test_initialization_defaults(self) -> None:
        """Test default initialization."""
        manager = AgentContextManager()
        self.assertEqual(manager.max_chunks_per_tool, 5)
        self.assertEqual(manager.max_total_chunks, 15)

    def test_initialization_custom(self) -> None:
        """Test custom initialization."""
        manager = AgentContextManager(
            max_chunks_per_tool=10,
            max_total_chunks=20,
        )
        self.assertEqual(manager.max_chunks_per_tool, 10)
        self.assertEqual(manager.max_total_chunks, 20)

    def test_initial_context_is_empty(self) -> None:
        """Test that initial context is empty."""
        self.assertEqual(len(self.manager.chunks), 0)
        self.assertEqual(len(self.manager.tool_calls), 0)

    # ------------------------------------------------------------------
    # Chunk deduplication tests
    # ------------------------------------------------------------------

    def test_add_chunks_deduplication(self) -> None:
        """Test that duplicate chunks are deduplicated."""
        chunk1 = _make_context_chunk(chunk_id="chunk-001", text="First")
        chunk2 = _make_context_chunk(chunk_id="chunk-001", text="First duplicate")

        self.manager.add_chunks([chunk1])
        self.manager.add_chunks([chunk2])

        self.assertEqual(len(self.manager.chunks), 1)
        self.assertEqual(self.manager.chunks[0].text, "First")

    def test_add_chunks_different_ids(self) -> None:
        """Test that different chunk IDs are kept."""
        chunk1 = _make_context_chunk(chunk_id="chunk-001", text="First")
        chunk2 = _make_context_chunk(chunk_id="chunk-002", text="Second")

        self.manager.add_chunks([chunk1])
        self.manager.add_chunks([chunk2])

        self.assertEqual(len(self.manager.chunks), 2)

    def test_add_chunks_multiple_same_call(self) -> None:
        """Test deduplication within same add call."""
        chunk1 = _make_context_chunk(chunk_id="chunk-001", text="First")
        chunk2 = _make_context_chunk(chunk_id="chunk-001", text="Duplicate")

        added = self.manager.add_chunks([chunk1, chunk2])

        self.assertEqual(len(added), 1)

    # ------------------------------------------------------------------
    # Max chunks limits tests
    # ------------------------------------------------------------------

    def test_max_total_chunks_limit(self) -> None:
        """Test that total chunks are limited."""
        for i in range(10):
            chunk = _make_context_chunk(
                chunk_id=f"chunk-{i:03d}",
                text=f"Chunk {i}",
                score=0.9 - (i * 0.05),
            )
            self.manager.add_chunks([chunk])

        self.assertLessEqual(len(self.manager.chunks), self.manager.max_total_chunks)

    def test_max_chunks_per_tool_limit(self) -> None:
        """Test that per-tool chunks are limited."""
        chunks = [
            _make_context_chunk(
                chunk_id=f"chunk-{i:03d}",
                text=f"Chunk {i}",
                score=0.9 - (i * 0.1),
            )
            for i in range(10)
        ]

        self.manager.add_chunks(chunks, tool_name="search_semantic", limit_per_tool=3)

        # Should only keep 3 from this tool
        self.assertLessEqual(len(self.manager.chunks), 3)

    def test_chunks_sorted_by_score_when_trimming(self) -> None:
        """Test that higher-scored chunks are kept when trimming."""
        low_score = _make_context_chunk(chunk_id="low", text="Low", score=0.3)
        high_score = _make_context_chunk(chunk_id="high", text="High", score=0.9)

        # Add low score first
        self.manager.add_chunks([low_score])

        # Add high score - should replace low if at limit
        manager = AgentContextManager(max_total_chunks=1)
        manager.add_chunks([low_score])
        manager.add_chunks([high_score])

        self.assertEqual(manager.chunks[0].chunk_id, "high")

    # ------------------------------------------------------------------
    # Query and iteration tests
    # ------------------------------------------------------------------

    def test_set_query(self) -> None:
        """Test setting the query."""
        self.manager.set_query("What decisions were made?")
        self.assertEqual(self.manager.context.query, "What decisions were made?")

    def test_increment_iteration(self) -> None:
        """Test incrementing iteration counter."""
        self.assertEqual(self.manager.context.iteration, 0)
        self.manager.increment_iteration()
        self.assertEqual(self.manager.context.iteration, 1)
        self.manager.increment_iteration()
        self.assertEqual(self.manager.context.iteration, 2)

    # ------------------------------------------------------------------
    # Tool call recording tests
    # ------------------------------------------------------------------

    def test_record_tool_call(self) -> None:
        """Test recording a tool call."""
        record = self.manager.record_tool_call(
            tool_name="search_semantic",
            arguments={"query": "test"},
            result_count=5,
        )

        self.assertIsInstance(record, ToolCallRecord)
        self.assertEqual(record.tool_name, "search_semantic")
        self.assertEqual(record.result_count, 5)
        self.assertEqual(len(self.manager.tool_calls), 1)

    def test_record_multiple_tool_calls(self) -> None:
        """Test recording multiple tool calls."""
        self.manager.record_tool_call(
            tool_name="search_semantic",
            arguments={"query": "test1"},
            result_count=3,
        )
        self.manager.record_tool_call(
            tool_name="search_keyword",
            arguments={"keyword": "test2"},
            result_count=2,
        )

        self.assertEqual(len(self.manager.tool_calls), 2)
        self.assertEqual(self.manager.tool_calls[0].tool_name, "search_semantic")
        self.assertEqual(self.manager.tool_calls[1].tool_name, "search_keyword")

    # ------------------------------------------------------------------
    # Context formatting tests
    # ------------------------------------------------------------------

    def test_format_context_for_llm_empty(self) -> None:
        """Test formatting empty context."""
        formatted = self.manager.format_context_for_llm()
        self.assertEqual(formatted, "")

    def test_format_context_for_llm_with_query(self) -> None:
        """Test formatting context with query."""
        self.manager.set_query("Test question")
        formatted = self.manager.format_context_for_llm()
        self.assertIn("User Query: Test question", formatted)

    def test_format_context_for_llm_with_chunks(self) -> None:
        """Test formatting context with chunks."""
        chunk = _make_context_chunk(
            text="Important decision made",
            source_type="transcript",
            section_type="analysis.decisions",
        )
        self.manager.add_chunks([chunk])

        formatted = self.manager.format_context_for_llm()
        self.assertIn("Retrieved Context:", formatted)
        self.assertIn("Important decision made", formatted)

    def test_format_context_for_llm_with_tool_history(self) -> None:
        """Test formatting context with tool call history."""
        self.manager.record_tool_call(
            tool_name="search_semantic",
            arguments={"query": "test"},
            result_count=3,
        )

        formatted = self.manager.format_context_for_llm(include_tool_history=True)
        self.assertIn("Tool Call History:", formatted)
        self.assertIn("search_semantic", formatted)

    def test_format_context_for_llm_without_tool_history(self) -> None:
        """Test formatting context without tool call history."""
        self.manager.record_tool_call(
            tool_name="search_semantic",
            arguments={"query": "test"},
            result_count=3,
        )

        formatted = self.manager.format_context_for_llm(include_tool_history=False)
        self.assertNotIn("Tool Call History:", formatted)

    # ------------------------------------------------------------------
    # Citation extraction tests
    # ------------------------------------------------------------------

    def test_extract_citations_empty(self) -> None:
        """Test extracting citations from empty context."""
        citations = self.manager.extract_citations()
        self.assertEqual(len(citations), 0)

    def test_extract_citations_with_chunks(self) -> None:
        """Test extracting citations from chunks."""
        chunk = _make_context_chunk(
            chunk_id="chunk-001",
            citation_ids=["cite-001", "cite-002"],
        )
        self.manager.add_chunks([chunk])

        citations = self.manager.extract_citations()
        self.assertEqual(len(citations), 2)
        self.assertIn("cite-001", [c["citation_id"] for c in citations])
        self.assertIn("cite-002", [c["citation_id"] for c in citations])

    def test_extract_citations_deduplication(self) -> None:
        """Test citation deduplication."""
        chunk1 = _make_context_chunk(
            chunk_id="chunk-001",
            citation_ids=["cite-001"],
        )
        chunk2 = _make_context_chunk(
            chunk_id="chunk-002",
            citation_ids=["cite-001"],  # Same citation
        )
        self.manager.add_chunks([chunk1, chunk2])

        citations = self.manager.extract_citations()
        # Should have 2 entries (different chunks, same citation)
        self.assertEqual(len(citations), 2)

    def test_extract_citations_structure(self) -> None:
        """Test citation structure."""
        chunk = _make_context_chunk(
            chunk_id="chunk-001",
            citation_ids=["cite-001"],
            source_type="transcript",
            section_type="summary.executive",
            segment_ids=["seg-001"],
        )
        self.manager.add_chunks([chunk])

        citations = self.manager.extract_citations()
        citation = citations[0]

        self.assertIn("chunk_id", citation)
        self.assertIn("citation_id", citation)
        self.assertIn("source_type", citation)
        self.assertIn("section_type", citation)
        self.assertIn("segment_ids", citation)

    # ------------------------------------------------------------------
    # Segment ID tests
    # ------------------------------------------------------------------

    def test_get_unique_segment_ids(self) -> None:
        """Test getting unique segment IDs."""
        chunk1 = _make_context_chunk(
            chunk_id="chunk-001",
            segment_ids=["seg-001", "seg-002"],
        )
        chunk2 = _make_context_chunk(
            chunk_id="chunk-002",
            segment_ids=["seg-002", "seg-003"],  # Duplicate seg-002
        )
        self.manager.add_chunks([chunk1, chunk2])

        segment_ids = self.manager.get_unique_segment_ids()
        self.assertEqual(len(segment_ids), 3)
        self.assertIn("seg-001", segment_ids)
        self.assertIn("seg-002", segment_ids)
        self.assertIn("seg-003", segment_ids)

    # ------------------------------------------------------------------
    # Reset tests
    # ------------------------------------------------------------------

    def test_reset(self) -> None:
        """Test resetting the context manager."""
        chunk = _make_context_chunk()
        self.manager.add_chunks([chunk])
        self.manager.set_query("Test")
        self.manager.increment_iteration()

        self.manager.reset()

        self.assertEqual(len(self.manager.chunks), 0)
        self.assertEqual(len(self.manager.tool_calls), 0)
        self.assertEqual(self.manager.context.query, "")
        self.assertEqual(self.manager.context.iteration, 0)

    # ------------------------------------------------------------------
    # Factory function test
    # ------------------------------------------------------------------

    def test_get_agent_context_manager_factory(self) -> None:
        """Test factory function."""
        manager = get_agent_context_manager(
            max_chunks_per_tool=10,
            max_total_chunks=20,
        )
        self.assertIsInstance(manager, AgentContextManager)
        self.assertEqual(manager.max_chunks_per_tool, 10)
        self.assertEqual(manager.max_total_chunks, 20)


if __name__ == "__main__":
    unittest.main()
