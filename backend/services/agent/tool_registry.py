"""
Agent Tool Registry for Agentic RAG system.

Provides tool definitions and execution for the LLM agent to perform
structured retrieval over meeting intelligence data.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from backend.models.meeting_models import MeetingChunkRecord
from backend.repositories.retrieval_repository import MeetingChunkRepository
from backend.services.retrieval_search_service import RetrievalSearchService


class ToolCategory(str, Enum):
    """Categories for organizing tools."""
    SEARCH = "search"
    RETRIEVAL = "retrieval"
    SYNTHESIS = "synthesis"


@dataclass(frozen=True)
class ToolParameter:
    """Definition of a tool parameter."""
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None
    enum: list[str] | None = None


@dataclass(frozen=True)
class ToolDefinition:
    """Definition of an agent tool."""
    name: str
    description: str
    category: ToolCategory
    parameters: list[ToolParameter]
    returns: str


@dataclass
class ToolExecutionResult:
    """Result of executing a tool."""
    tool_name: str
    success: bool
    data: list[dict[str, Any]] | dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None


def _chunk_to_dict(chunk: MeetingChunkRecord) -> dict[str, Any]:
    """Convert a MeetingChunkRecord to a dictionary for serialization."""
    return {
        "chunkId": chunk.chunk_id,
        "meetingId": chunk.meeting_id,
        "sectionType": chunk.section_type,
        "sourceType": chunk.source_type,
        "text": chunk.text,
        "jsonPointer": chunk.json_pointer,
        "startMs": chunk.start_ms,
        "endMs": chunk.end_ms,
        "citationIds": chunk.citation_ids or [],
        "segmentIds": chunk.segment_ids or [],
        "metadata": chunk.metadata_json or {},
    }


class AgentToolRegistry:
    """
    Registry of tools available to the RAG agent.

    Provides tool definitions for the LLM to select from and handles
    execution of those tools against the retrieval system.
    """

    # Section type constants for direct retrieval
    SECTION_SUMMARY_EXECUTIVE = "summary.executive"
    SECTION_SUMMARY_DETAILED = "summary.detailed"
    SECTION_SUMMARY_KEY_POINTS = "summary.keyPoints"
    SECTION_ANALYSIS_ACTION_ITEMS = "analysis.actionItems"
    SECTION_ANALYSIS_DECISIONS = "analysis.decisions"
    SECTION_ANALYSIS_RISKS = "analysis.risks"
    SECTION_ANALYSIS_BLOCKERS = "analysis.blockers"
    SECTION_ANALYSIS_TIMELINE = "analysis.timeline"
    SECTION_PARTICIPANTS_OVERVIEW = "participants.overview"
    SECTION_PARTICIPANTS_PARTICIPANT = "participants.participant"

    def __init__(
        self,
        session: Session,
        retrieval_search: RetrievalSearchService | None = None,
    ) -> None:
        """
        Initialize the tool registry.

        Args:
            session: SQLAlchemy session for database operations
            retrieval_search: Optional RetrievalSearchService instance (created if not provided)
        """
        self.session = session
        self.chunks = MeetingChunkRepository(session)
        self.retrieval_search = retrieval_search or RetrievalSearchService(session)

    def get_tools(self) -> list[dict[str, Any]]:
        """
        Get all tool definitions in a format suitable for LLM function calling.

        Returns:
            List of tool definition dictionaries
        """
        return [
            self._tool_to_dict(definition)
            for definition in self._get_all_definitions()
        ]

    def get_tool_by_name(self, name: str) -> ToolDefinition | None:
        """
        Get a tool definition by name.

        Args:
            name: The tool name to look up

        Returns:
            ToolDefinition if found, None otherwise
        """
        for definition in self._get_all_definitions():
            if definition.name == name:
                return definition
        return None

    def execute_tool(
        self,
        *,
        meeting_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        workspace_id: str | None = None,
    ) -> ToolExecutionResult:
        """
        Execute a tool with the given arguments.

        Args:
            meeting_id: The meeting ID to operate on
            tool_name: Name of the tool to execute
            arguments: Tool-specific arguments
            workspace_id: Optional workspace ID (defaults to meeting_id if not provided)

        Returns:
            ToolExecutionResult with the tool's output or error
        """
        # Validate tool name exists
        definition = self.get_tool_by_name(tool_name)
        if definition is None:
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                error=f"Unknown tool: '{tool_name}'. Valid tools are: {', '.join(d.name for d in self._get_all_definitions())}",
            )

        effective_workspace_id = workspace_id or meeting_id

        try:
            # Dispatch table for tool execution
            executors = {
                "search_semantic": self._execute_search_semantic,
                "search_keyword": self._execute_search_keyword,
                "search_section": self._execute_search_section,
                "search_speaker": self._execute_search_speaker,
                "get_summary": self._execute_get_summary,
                "get_action_items": self._execute_get_action_items,
                "get_decisions": self._execute_get_decisions,
                "get_risks": self._execute_get_risks,
                "get_timeline": self._execute_get_timeline,
                "get_participants": self._execute_get_participants,
                "synthesize_answer": self._execute_synthesize_answer,
            }

            executor = executors.get(tool_name)
            if executor is None:
                return ToolExecutionResult(
                    tool_name=tool_name,
                    success=False,
                    error=f"Tool '{tool_name}' is defined but has no executor.",
                )

            # Call executor based on signature
            if tool_name in {"search_semantic"}:
                return executor(
                    meeting_id=meeting_id,
                    workspace_id=effective_workspace_id,
                    arguments=arguments,
                )
            elif tool_name in {"get_summary"}:
                return executor(
                    meeting_id=meeting_id,
                    arguments=arguments,
                )
            elif tool_name in {"search_keyword", "search_section", "search_speaker"}:
                return executor(
                    meeting_id=meeting_id,
                    arguments=arguments,
                )
            elif tool_name in {"synthesize_answer"}:
                return executor(
                    arguments=arguments,
                )
            else:
                # get_action_items, get_decisions, get_risks, get_timeline, get_participants
                return executor(
                    meeting_id=meeting_id,
                )
        except Exception as exc:
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                error=f"Error executing tool '{tool_name}': {str(exc)}",
            )

    # ─── Tool Definitions ─────────────────────────────────────────────

    def _get_all_definitions(self) -> list[ToolDefinition]:
        """Get all tool definitions."""
        return [
            self._def_search_semantic(),
            self._def_search_keyword(),
            self._def_search_section(),
            self._def_search_speaker(),
            self._def_get_summary(),
            self._def_get_action_items(),
            self._def_get_decisions(),
            self._def_get_risks(),
            self._def_get_timeline(),
            self._def_get_participants(),
            self._def_synthesize_answer(),
        ]

    def _def_search_semantic(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_semantic",
            description="Search meeting content using semantic vector similarity. Best for finding conceptually related content even when exact keywords don't match.",
            category=ToolCategory.SEARCH,
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="Natural language query to search for",
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="Maximum number of results to return",
                    required=False,
                    default=6,
                ),
            ],
            returns="List of semantically matching chunks with relevance scores",
        )

    def _def_search_keyword(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_keyword",
            description="Search meeting content using exact keyword matching (ILIKE). Best for finding specific terms, names, or exact phrases.",
            category=ToolCategory.SEARCH,
            parameters=[
                ToolParameter(
                    name="keyword",
                    type="string",
                    description="Keyword or phrase to search for",
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="Maximum number of results to return",
                    required=False,
                    default=10,
                ),
            ],
            returns="List of chunks containing the keyword",
        )

    def _def_search_section(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_section",
            description="Search within a specific section type of the meeting intelligence. Use for targeted retrieval from known sections.",
            category=ToolCategory.SEARCH,
            parameters=[
                ToolParameter(
                    name="section_type",
                    type="string",
                    description="Section type to search within",
                    enum=[
                        "summary.executive",
                        "summary.detailed",
                        "summary.keyPoints",
                        "analysis.actionItems",
                        "analysis.decisions",
                        "analysis.risks",
                        "analysis.blockers",
                        "analysis.timeline",
                        "analysis.followUps",
                        "analysis.openQuestions",
                        "analysis.requirements",
                        "analysis.constraints",
                        "analysis.topics",
                        "participants.overview",
                        "participants.participant",
                    ],
                ),
                ToolParameter(
                    name="query",
                    type="string",
                    description="Optional search query within the section",
                    required=False,
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="Maximum number of results to return",
                    required=False,
                    default=10,
                ),
            ],
            returns="List of chunks from the specified section type",
        )

    def _def_search_speaker(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_speaker",
            description="Search for content related to a specific speaker or participant in the meeting.",
            category=ToolCategory.SEARCH,
            parameters=[
                ToolParameter(
                    name="speaker_query",
                    type="string",
                    description="Speaker name or role to search for",
                ),
                ToolParameter(
                    name="limit",
                    type="integer",
                    description="Maximum number of results to return",
                    required=False,
                    default=10,
                ),
            ],
            returns="List of chunks related to the specified speaker",
        )

    def _def_get_summary(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_summary",
            description="Retrieve the meeting summary sections. Returns executive summary, detailed summary, and/or key points.",
            category=ToolCategory.RETRIEVAL,
            parameters=[
                ToolParameter(
                    name="summary_type",
                    type="string",
                    description="Type of summary to retrieve",
                    required=False,
                    default="all",
                    enum=["executive", "detailed", "key_points", "all"],
                ),
            ],
            returns="Summary sections of the meeting",
        )

    def _def_get_action_items(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_action_items",
            description="Retrieve action items and follow-up tasks identified in the meeting.",
            category=ToolCategory.RETRIEVAL,
            parameters=[],
            returns="Action items and follow-ups from the meeting",
        )

    def _def_get_decisions(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_decisions",
            description="Retrieve decisions and outcomes made during the meeting.",
            category=ToolCategory.RETRIEVAL,
            parameters=[],
            returns="Decisions and outcomes from the meeting",
        )

    def _def_get_risks(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_risks",
            description="Retrieve risks, blockers, and open questions identified in the meeting.",
            category=ToolCategory.RETRIEVAL,
            parameters=[],
            returns="Risks, blockers, and open questions from the meeting",
        )

    def _def_get_timeline(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_timeline",
            description="Retrieve timeline and deadline information from the meeting.",
            category=ToolCategory.RETRIEVAL,
            parameters=[],
            returns="Timeline and deadline information from the meeting",
        )

    def _def_get_participants(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_participants",
            description="Retrieve participant information including names, roles, and overview.",
            category=ToolCategory.RETRIEVAL,
            parameters=[],
            returns="Participant details from the meeting",
        )

    def _def_synthesize_answer(self) -> ToolDefinition:
        return ToolDefinition(
            name="synthesize_answer",
            description="Trigger final answer synthesis from gathered information. This signals the agent has collected enough context and is ready to generate the response.",
            category=ToolCategory.SYNTHESIS,
            parameters=[
                ToolParameter(
                    name="answer",
                    type="string",
                    description="The synthesized answer based on gathered information",
                ),
                ToolParameter(
                    name="citations",
                    type="array",
                    description="List of chunk IDs used as citations",
                    required=False,
                ),
            ],
            returns="Confirmation that answer synthesis was triggered",
        )

    # ─── Tool Execution Handlers ──────────────────────────────────────

    def _execute_search_semantic(
        self,
        *,
        meeting_id: str,
        workspace_id: str,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        """Execute semantic vector search."""
        query = arguments.get("query")
        if not query:
            return ToolExecutionResult(
                tool_name="search_semantic",
                success=False,
                error="Missing required parameter: 'query'",
            )

        limit = arguments.get("limit", 6)

        results = self.retrieval_search.search_meeting(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            query=query,
            limit=limit,
        )

        return ToolExecutionResult(
            tool_name="search_semantic",
            success=True,
            data=[
                {
                    **_chunk_to_dict(result.record if hasattr(result, "record") else result),
                    "score": getattr(result, "score", 0.0),
                }
                for result in results
            ],
            metadata={
                "query": query,
                "resultCount": len(results),
                "searchType": "semantic",
            },
        )

    def _execute_search_keyword(
        self,
        *,
        meeting_id: str,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        """Execute keyword ILIKE search."""
        keyword = arguments.get("keyword")
        if not keyword:
            return ToolExecutionResult(
                tool_name="search_keyword",
                success=False,
                error="Missing required parameter: 'keyword'",
            )

        limit = arguments.get("limit", 10)

        results = self.chunks.search_by_keyword(
            meeting_id=meeting_id,
            keyword=keyword,
            limit=limit,
        )

        return ToolExecutionResult(
            tool_name="search_keyword",
            success=True,
            data=[_chunk_to_dict(chunk) for chunk in results],
            metadata={
                "keyword": keyword,
                "resultCount": len(results),
                "searchType": "keyword",
            },
        )

    def _execute_search_section(
        self,
        *,
        meeting_id: str,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        """Execute section type search."""
        section_type = arguments.get("section_type")
        if not section_type:
            return ToolExecutionResult(
                tool_name="search_section",
                success=False,
                error="Missing required parameter: 'section_type'",
            )

        # Validate section_type against allowed enum
        valid_sections = {
            "summary.executive",
            "summary.detailed",
            "summary.keyPoints",
            "analysis.actionItems",
            "analysis.decisions",
            "analysis.risks",
            "analysis.blockers",
            "analysis.timeline",
            "analysis.followUps",
            "analysis.openQuestions",
            "analysis.requirements",
            "analysis.constraints",
            "analysis.topics",
            "participants.overview",
            "participants.participant",
        }
        if section_type not in valid_sections:
            return ToolExecutionResult(
                tool_name="search_section",
                success=False,
                error=f"Invalid section_type '{section_type}'. Valid types: {', '.join(sorted(valid_sections))}",
            )

        query = arguments.get("query")
        limit = arguments.get("limit", 10)

        if query:
            # If query provided, use keyword search within section
            all_chunks = self.chunks.list_by_section_type(
                meeting_id=meeting_id,
                section_type=section_type,
                limit=limit * 2,  # Get more to filter
            )
            # Filter by query match
            query_lower = query.lower()
            results = [
                chunk for chunk in all_chunks
                if query_lower in chunk.text.lower()
            ][:limit]
        else:
            results = self.chunks.list_by_section_type(
                meeting_id=meeting_id,
                section_type=section_type,
                limit=limit,
            )

        return ToolExecutionResult(
            tool_name="search_section",
            success=True,
            data=[_chunk_to_dict(chunk) for chunk in results],
            metadata={
                "sectionType": section_type,
                "query": query,
                "resultCount": len(results),
                "searchType": "section",
            },
        )

    def _execute_search_speaker(
        self,
        *,
        meeting_id: str,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        """Execute speaker search."""
        speaker_query = arguments.get("speaker_query")
        if not speaker_query:
            return ToolExecutionResult(
                tool_name="search_speaker",
                success=False,
                error="Missing required parameter: 'speaker_query'",
            )

        limit = arguments.get("limit", 10)

        results = self.chunks.search_by_speaker(
            meeting_id=meeting_id,
            query=speaker_query,
            limit=limit,
        )

        return ToolExecutionResult(
            tool_name="search_speaker",
            success=True,
            data=[_chunk_to_dict(chunk) for chunk in results],
            metadata={
                "speakerQuery": speaker_query,
                "resultCount": len(results),
                "searchType": "speaker",
            },
        )

    def _execute_get_summary(
        self,
        *,
        meeting_id: str,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        """Retrieve summary sections."""
        summary_type = arguments.get("summary_type", "all")

        if summary_type == "executive":
            section_types = [self.SECTION_SUMMARY_EXECUTIVE]
        elif summary_type == "detailed":
            section_types = [self.SECTION_SUMMARY_DETAILED]
        elif summary_type == "key_points":
            section_types = [self.SECTION_SUMMARY_KEY_POINTS]
        else:
            section_types = [
                self.SECTION_SUMMARY_EXECUTIVE,
                self.SECTION_SUMMARY_DETAILED,
                self.SECTION_SUMMARY_KEY_POINTS,
            ]

        results = self.chunks.get_structured_sections(
            meeting_id=meeting_id,
            section_types=section_types,
        )

        return ToolExecutionResult(
            tool_name="get_summary",
            success=True,
            data=[_chunk_to_dict(chunk) for chunk in results],
            metadata={
                "summaryType": summary_type,
                "sectionTypes": section_types,
                "resultCount": len(results),
            },
        )

    def _execute_get_action_items(self, *, meeting_id: str) -> ToolExecutionResult:
        """Retrieve action items."""
        results = self.chunks.get_structured_sections(
            meeting_id=meeting_id,
            section_types=[
                self.SECTION_ANALYSIS_ACTION_ITEMS,
                "analysis.followUps",
            ],
        )

        return ToolExecutionResult(
            tool_name="get_action_items",
            success=True,
            data=[_chunk_to_dict(chunk) for chunk in results],
            metadata={
                "resultCount": len(results),
            },
        )

    def _execute_get_decisions(self, *, meeting_id: str) -> ToolExecutionResult:
        """Retrieve decisions."""
        results = self.chunks.get_structured_sections(
            meeting_id=meeting_id,
            section_types=[
                self.SECTION_ANALYSIS_DECISIONS,
                "analysis.outcomes",
            ],
        )

        return ToolExecutionResult(
            tool_name="get_decisions",
            success=True,
            data=[_chunk_to_dict(chunk) for chunk in results],
            metadata={
                "resultCount": len(results),
            },
        )

    def _execute_get_risks(self, *, meeting_id: str) -> ToolExecutionResult:
        """Retrieve risks, blockers, and open questions."""
        results = self.chunks.get_structured_sections(
            meeting_id=meeting_id,
            section_types=[
                self.SECTION_ANALYSIS_RISKS,
                self.SECTION_ANALYSIS_BLOCKERS,
                "analysis.openQuestions",
            ],
        )

        return ToolExecutionResult(
            tool_name="get_risks",
            success=True,
            data=[_chunk_to_dict(chunk) for chunk in results],
            metadata={
                "resultCount": len(results),
            },
        )

    def _execute_get_timeline(self, *, meeting_id: str) -> ToolExecutionResult:
        """Retrieve timeline information."""
        results = self.chunks.get_structured_sections(
            meeting_id=meeting_id,
            section_types=[
                self.SECTION_ANALYSIS_TIMELINE,
                "analysis.followUps",
            ],
        )

        return ToolExecutionResult(
            tool_name="get_timeline",
            success=True,
            data=[_chunk_to_dict(chunk) for chunk in results],
            metadata={
                "resultCount": len(results),
            },
        )

    def _execute_get_participants(self, *, meeting_id: str) -> ToolExecutionResult:
        """Retrieve participant information."""
        results = self.chunks.get_structured_sections(
            meeting_id=meeting_id,
            section_types=[
                self.SECTION_PARTICIPANTS_OVERVIEW,
                self.SECTION_PARTICIPANTS_PARTICIPANT,
            ],
        )

        return ToolExecutionResult(
            tool_name="get_participants",
            success=True,
            data=[_chunk_to_dict(chunk) for chunk in results],
            metadata={
                "resultCount": len(results),
            },
        )

    def _execute_synthesize_answer(
        self,
        *,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        """Handle answer synthesis trigger."""
        answer = arguments.get("answer")
        if not answer:
            return ToolExecutionResult(
                tool_name="synthesize_answer",
                success=False,
                error="Missing required parameter: 'answer'",
            )

        citations = arguments.get("citations", [])

        return ToolExecutionResult(
            tool_name="synthesize_answer",
            success=True,
            data={
                "answer": answer,
                "citations": citations,
                "status": "synthesized",
            },
            metadata={
                "citationCount": len(citations),
                "answerLength": len(answer),
            },
        )

    # ─── Helper Methods ───────────────────────────────────────────────

    def _tool_to_dict(self, definition: ToolDefinition) -> dict[str, Any]:
        """Convert a ToolDefinition to a dictionary for LLM function calling."""
        properties = {}
        required = []

        for param in definition.parameters:
            param_def: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                param_def["enum"] = param.enum
            if param.default is not None:
                param_def["default"] = param.default

            properties[param.name] = param_def

            if param.required:
                required.append(param.name)

        result: dict[str, Any] = {
            "type": "function",
            "function": {
                "name": definition.name,
                "description": definition.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                },
            },
        }

        if required:
            result["function"]["parameters"]["required"] = required

        return result


def create_tool_registry(
    session: Session,
    retrieval_search: RetrievalSearchService | None = None,
) -> AgentToolRegistry:
    """
    Factory function to create an AgentToolRegistry instance.

    Args:
        session: SQLAlchemy session
        retrieval_search: Optional RetrievalSearchService instance

    Returns:
        AgentToolRegistry instance
    """
    return AgentToolRegistry(
        session=session,
        retrieval_search=retrieval_search,
    )
