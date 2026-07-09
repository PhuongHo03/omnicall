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
from backend.services.agent_tool_registry import (
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
        self.workspace_id = "test-workspace-001"
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

    def test_get_tools_contains_search_section(self) -> None:
        """Test that tools list contains search_section."""
        tools = self.registry.get_tools()
        tool_names = [t["function"]["name"] for t in tools]
        self.assertIn("search_section", tool_names)

    def test_get_tools_contains_search_speaker(self) -> None:
        """Test that tools list contains search_speaker."""
        tools = self.registry.get_tools()
        tool_names = [t["function"]["name"] for t in tools]
        self.assertIn("search_speaker", tool_names)

    def test_get_tools_contains_get_summary(self) -> None:
        """Test that tools list contains get_summary."""
        tools = self.registry.get_tools()
        tool_names = [t["function"]["name"] for t in tools]
        self.assertIn("get_summary", tool_names)

    def test_get_tools_contains_get_action_items(self) -> None:
        """Test that tools list contains get_action_items."""
        tools = self.registry.get_tools()
        tool_names = [t["function"]["name"] for t in tools]
        self.assertIn("get_action_items", tool_names)

    def test_get_tools_contains_get_decisions(self) -> None:
        """Test that tools list contains get_decisions."""
        tools = self.registry.get_tools()
        tool_names = [t["function"]["name"] for t in tools]
        self.assertIn("get_decisions", tool_names)

    def test_get_tools_contains_get_risks(self) -> None:
        """Test that tools list contains get_risks."""
        tools = self.registry.get_tools()
        tool_names = [t["function"]["name"] for t in tools]
        self.assertIn("get_risks", tool_names)

    def test_get_tools_contains_get_timeline(self) -> None:
        """Test that tools list contains get_timeline."""
        tools = self.registry.get_tools()
        tool_names = [t["function"]["name"] for t in tools]
        self.assertIn("get_timeline", tool_names)

    def test_get_tools_contains_get_participants(self) -> None:
        """Test that tools list contains get_participants."""
        tools = self.registry.get_tools()
        tool_names = [t["function"]["name"] for t in tools]
        self.assertIn("get_participants", tool_names)

    def test_get_tools_contains_synthesize_answer(self) -> None:
        """Test that tools list contains synthesize_answer."""
        tools = self.registry.get_tools()
        tool_names = [t["function"]["name"] for t in tools]
        self.assertIn("synthesize_answer", tool_names)

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
            workspace_id=self.workspace_id,
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

    def test_execute_search_section(self) -> None:
        """Test executing search_section tool."""
        chunk = _make_meeting_chunk(section_type="analysis.actionItems")
        self.registry.chunks.get_structured_sections.return_value = [chunk]

        result = self.registry.execute_tool(
            meeting_id=self.meeting_id,
            tool_name="search_section",
            arguments={"section_type": "analysis.actionItems"},
        )

        self.assertIsInstance(result, ToolExecutionResult)
        self.assertTrue(result.success)
        self.assertEqual(result.tool_name, "search_section")

    def test_execute_search_speaker(self) -> None:
        """Test executing search_speaker tool."""
        chunk = _make_meeting_chunk()
        self.registry.chunks.search_by_speaker.return_value = [chunk]

        result = self.registry.execute_tool(
            meeting_id=self.meeting_id,
            tool_name="search_speaker",
            arguments={"speaker_query": "Alice"},
        )

        self.assertIsInstance(result, ToolExecutionResult)
        self.assertTrue(result.success)
        self.assertEqual(result.tool_name, "search_speaker")

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

    def test_execute_get_action_items(self) -> None:
        """Test executing get_action_items tool."""
        chunk = _make_meeting_chunk(section_type="analysis.actionItems")
        self.registry.chunks.get_structured_sections.return_value = [chunk]

        result = self.registry.execute_tool(
            meeting_id=self.meeting_id,
            tool_name="get_action_items",
            arguments={},
        )

        self.assertIsInstance(result, ToolExecutionResult)
        self.assertTrue(result.success)
        self.assertEqual(result.tool_name, "get_action_items")

    def test_execute_get_decisions(self) -> None:
        """Test executing get_decisions tool."""
        chunk = _make_meeting_chunk(section_type="analysis.decisions")
        self.registry.chunks.get_structured_sections.return_value = [chunk]

        result = self.registry.execute_tool(
            meeting_id=self.meeting_id,
            tool_name="get_decisions",
            arguments={},
        )

        self.assertIsInstance(result, ToolExecutionResult)
        self.assertTrue(result.success)
        self.assertEqual(result.tool_name, "get_decisions")

    def test_execute_get_risks(self) -> None:
        """Test executing get_risks tool."""
        chunk = _make_meeting_chunk(section_type="analysis.risks")
        self.registry.chunks.get_structured_sections.return_value = [chunk]

        result = self.registry.execute_tool(
            meeting_id=self.meeting_id,
            tool_name="get_risks",
            arguments={},
        )

        self.assertIsInstance(result, ToolExecutionResult)
        self.assertTrue(result.success)
        self.assertEqual(result.tool_name, "get_risks")

    def test_execute_get_timeline(self) -> None:
        """Test executing get_timeline tool."""
        chunk = _make_meeting_chunk(section_type="analysis.timeline")
        self.registry.chunks.get_structured_sections.return_value = [chunk]

        result = self.registry.execute_tool(
            meeting_id=self.meeting_id,
            tool_name="get_timeline",
            arguments={},
        )

        self.assertIsInstance(result, ToolExecutionResult)
        self.assertTrue(result.success)
        self.assertEqual(result.tool_name, "get_timeline")

    def test_execute_get_participants(self) -> None:
        """Test executing get_participants tool."""
        chunk = _make_meeting_chunk(section_type="participants.participant")
        self.registry.chunks.get_structured_sections.return_value = [chunk]

        result = self.registry.execute_tool(
            meeting_id=self.meeting_id,
            tool_name="get_participants",
            arguments={},
        )

        self.assertIsInstance(result, ToolExecutionResult)
        self.assertTrue(result.success)
        self.assertEqual(result.tool_name, "get_participants")

    def test_execute_synthesize_answer(self) -> None:
        """Test executing synthesize_answer tool."""
        result = self.registry.execute_tool(
            meeting_id=self.meeting_id,
            tool_name="synthesize_answer",
            arguments={"answer": "Test answer", "citations": ["cite-001"]},
        )

        self.assertIsInstance(result, ToolExecutionResult)
        self.assertTrue(result.success)
        self.assertEqual(result.tool_name, "synthesize_answer")
        self.assertEqual(result.data["answer"], "Test answer")

    def test_execute_synthesize_answer_missing_answer(self) -> None:
        """Test synthesize_answer with missing answer parameter."""
        result = self.registry.execute_tool(
            meeting_id=self.meeting_id,
            tool_name="synthesize_answer",
            arguments={},
        )

        self.assertIsInstance(result, ToolExecutionResult)
        self.assertFalse(result.success)
        self.assertIn("Missing required parameter", result.error)

    def test_tool_error_handling(self) -> None:
        """Test tool execution error handling."""
        self.registry.retrieval_search.search_meeting.side_effect = Exception("DB error")

        result = self.registry.execute_tool(
            meeting_id=self.meeting_id,
            tool_name="search_semantic",
            arguments={"query": "test"},
            workspace_id=self.workspace_id,
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
