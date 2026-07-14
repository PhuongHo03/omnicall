"""Tests for AgentToolRegistry — Tool definitions and execution.

Covers:
- Test each tool individually (search_semantic, search_keyword, etc.)
- Test tool validation (prevent hallucinated tools)
- Test tool error handling
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from backend.models.meeting_models import MeetingChunkRecord
from backend.services.agent.tool_registry import (
    AgentToolRegistry,
    ToolCategory,
    ToolDefinition,
    ToolExecutionResult,
    ToolParameter,
    create_tool_registry,
)


def _make_meeting_chunk(
    chunk_id: str = "chunk-001",
    meeting_id: str = "meeting-001",
    text: str = "Sample text",
    section_type: str = "summary.executive",
    source_type: str = "transcript",
) -> MeetingChunkRecord:
    """Create a MeetingChunkRecord for testing."""
    chunk = MagicMock(spec=MeetingChunkRecord)
    chunk.chunk_id = chunk_id
    chunk.meeting_id = meeting_id
    chunk.text = text
    chunk.section_type = section_type
    chunk.source_type = source_type
    chunk.citation_ids = ["cite-001"]
    chunk.segment_ids = ["seg-001"]
    chunk.start_ms = 0
    chunk.end_ms = 1000
    chunk.metadata_json = {"title": "Test"}
    chunk.json_pointer = f"/chunks/{chunk_id}"
    return chunk


class AgentToolRegistryTestCase(unittest.TestCase):
    """Test cases for AgentToolRegistry."""

    def setUp(self) -> None:
        self.session = MagicMock()
        self.meeting_id = "test-meeting-001"
        self.registry = AgentToolRegistry(
            session=self.session,
            retrieval_search=MagicMock(),
        )
        self.registry.chunks = MagicMock()

    def test_get_tools_returns_list(self) -> None:
        """Test that get_tools returns a list of tool definitions."""
        tools = self.registry.get_tools()
        self.assertIsInstance(tools, list)
        self.assertGreater(len(tools), 0)

    def test_get_tools_contains_search_semantic(self) -> None:
        """Test that tools list contains search_semantic."""
        tools = self.registry.get_tools()
        tool_names = [t["function"]["name"] for t in tools]
        self.assertIn("search_semantic", tool_names)

    def test_get_tools_contains_search_keyword(self) -> None:
        """Test that tools list contains search_keyword."""
        tools = self.registry.get_tools()
        tool_names = [t["function"]["name"] for t in tools]
        self.assertIn("search_keyword", tool_names)

    def test_get_tools_contains_search_records(self) -> None:
        tools = self.registry.get_tools()
        tool_names = [t["function"]["name"] for t in tools]
        self.assertIn("search_records", tool_names)

    def test_get_tools_contains_search_section(self) -> None:
        """Test that tools list contains search_section."""
        tools = self.registry.get_tools()
        tool_names = [t["function"]["name"] for t in tools]
        self.assertIn("search_section", tool_names)

    def test_get_tools_contains_get_summary(self) -> None:
        """Test that tools list contains get_summary."""
        tools = self.registry.get_tools()
        tool_names = [t["function"]["name"] for t in tools]
        self.assertIn("get_summary", tool_names)

    def test_get_tools_does_not_contain_synthesize_answer(self) -> None:
        """Synthesis is a service boundary, not an LLM retrieval tool."""
        tools = self.registry.get_tools()
        tool_names = [t["function"]["name"] for t in tools]
        self.assertNotIn("synthesize_answer", tool_names)

    def test_get_tool_by_name_found(self) -> None:
        """Test getting a tool definition by name."""
        tool = self.registry.get_tool_by_name("search_semantic")
        self.assertIsNotNone(tool)
        self.assertEqual(tool.name, "search_semantic")

    def test_get_tool_by_name_not_found(self) -> None:
        """Test getting a non-existent tool returns None."""
        tool = self.registry.get_tool_by_name("nonexistent_tool")
        self.assertIsNone(tool)

    def test_execute_tool_unknown_tool(self) -> None:
        """Test executing an unknown tool returns error."""
        result = self.registry.execute_tool(
            meeting_id=self.meeting_id,
            tool_name="hallucinated_tool",
            arguments={},
        )
        self.assertIsInstance(result, ToolExecutionResult)
        self.assertFalse(result.success)
        self.assertIn("Unknown tool", result.error)

    def test_execute_search_semantic(self) -> None:
        """Test executing search_semantic tool."""
        chunk = _make_meeting_chunk()
        self.registry.retrieval_search.search_meeting.return_value = [chunk]

        result = self.registry.execute_tool(
            meeting_id=self.meeting_id,
            tool_name="search_semantic",
            arguments={"query": "test query", "limit": 5},
        )

        self.assertIsInstance(result, ToolExecutionResult)
        self.assertTrue(result.success)
        self.assertEqual(result.tool_name, "search_semantic")

    def test_execute_search_keyword(self) -> None:
        """Test executing search_keyword tool."""
        chunk = _make_meeting_chunk()
        self.registry.chunks.search_by_keyword.return_value = [chunk]

        result = self.registry.execute_tool(
            meeting_id=self.meeting_id,
            tool_name="search_keyword",
            arguments={"keyword": "decision"},
        )

        self.assertIsInstance(result, ToolExecutionResult)
        self.assertTrue(result.success)
        self.assertEqual(result.tool_name, "search_keyword")

    def test_execute_search_keyword_prefers_normalized_query(self) -> None:
        chunk = _make_meeting_chunk()
        self.registry.chunks.search_by_keyword.return_value = [chunk]

        result = self.registry.execute_tool(
            meeting_id=self.meeting_id,
            tool_name="search_keyword",
            arguments={"query": "price OR cost", "keyword": "giá tiền"},
        )

        self.assertTrue(result.success)
        self.registry.chunks.search_by_keyword.assert_called_once_with(
            meeting_id=self.meeting_id,
            keyword="price OR cost",
            limit=10,
        )

    def test_execute_search_records_filters_canonical_metadata(self) -> None:
        chunk = _make_meeting_chunk(section_type="fact.record")
        chunk.metadata_json = {"recordId": "fact-1", "recordType": "fact", "subtype": "participant_count"}
        self.registry.chunks.list_for_meeting.return_value = [chunk]
        result = self.registry.execute_tool(
            meeting_id=self.meeting_id,
            tool_name="search_records",
            arguments={"record_type": "fact", "subtype": "participant_count"},
        )
        self.assertTrue(result.success)
        self.assertEqual(len(result.data), 1)

    def test_execute_search_section(self) -> None:
        """Test executing search_section tool."""
        chunk = _make_meeting_chunk(section_type="action.item")
        self.registry.chunks.get_structured_sections.return_value = [chunk]

        result = self.registry.execute_tool(
            meeting_id=self.meeting_id,
            tool_name="search_section",
            arguments={"section_type": "action.item"},
        )

        self.assertIsInstance(result, ToolExecutionResult)
        self.assertTrue(result.success)
        self.assertEqual(result.tool_name, "search_section")

    def test_execute_get_summary(self) -> None:
        """Test executing get_summary tool."""
        chunk = _make_meeting_chunk(section_type="summary.executive")
        self.registry.chunks.get_structured_sections.return_value = [chunk]

        result = self.registry.execute_tool(
            meeting_id=self.meeting_id,
            tool_name="get_summary",
            arguments={},
        )

        self.assertIsInstance(result, ToolExecutionResult)
        self.assertTrue(result.success)
        self.assertEqual(result.tool_name, "get_summary")

    def test_tool_error_handling(self) -> None:
        """Test tool execution error handling."""
        self.registry.retrieval_search.search_meeting.side_effect = Exception("DB error")

        result = self.registry.execute_tool(
            meeting_id=self.meeting_id,
            tool_name="search_semantic",
            arguments={"query": "test"},
        )

        self.assertIsInstance(result, ToolExecutionResult)
        self.assertFalse(result.success)
        self.assertIn("DB error", result.error)

    def test_tool_definition_structure(self) -> None:
        """Test that tool definitions have correct structure."""
        tools = self.registry.get_tools()
        for tool in tools:
            self.assertIn("type", tool)
            self.assertEqual(tool["type"], "function")
            self.assertIn("function", tool)
            self.assertIn("name", tool["function"])
            self.assertIn("description", tool["function"])
            self.assertIn("parameters", tool["function"])

    def test_create_tool_registry_factory(self) -> None:
        """Test factory function creates registry."""
        registry = create_tool_registry(session=self.session)
        self.assertIsInstance(registry, AgentToolRegistry)


if __name__ == "__main__":
    unittest.main()
