"""Static catalog of tools exposed to the Agentic RAG loop."""

from backend.services.agent.tool_definitions import (
    ToolCategory,
    ToolDefinition,
    ToolParameter,
)
from backend.services.retrieval.section_registry import SECTION_TYPES


def get_tool_definitions() -> list[ToolDefinition]:
    """Return the stable tool contract advertised to the language model."""
    return [
        ToolDefinition(
            name="search_semantic",
            description="Search meeting content using semantic vector similarity. Best for finding conceptually related content even when exact keywords don't match.",
            category=ToolCategory.SEARCH,
            parameters=[
                ToolParameter("query", "string", "Natural language query to search for"),
                ToolParameter("limit", "integer", "Maximum number of results to return", required=False, default=6),
            ],
            returns="List of semantically matching chunks with relevance scores",
        ),
        ToolDefinition(
            name="search_keyword",
            description="Search meeting content using exact keyword matching (ILIKE). Best for finding specific terms, names, or exact phrases.",
            category=ToolCategory.SEARCH,
            parameters=[
                ToolParameter("keyword", "string", "Keyword or phrase to search for"),
                ToolParameter("limit", "integer", "Maximum number of results to return", required=False, default=10),
            ],
            returns="List of chunks containing the keyword",
        ),
        ToolDefinition(
            name="search_section",
            description="Search within a specific section type of the meeting intelligence. Use for targeted retrieval from known sections.",
            category=ToolCategory.SEARCH,
            parameters=[
                ToolParameter(
                    "section_type",
                    "string",
                    "Section type to search within",
                    enum=list(SECTION_TYPES),
                ),
                ToolParameter("query", "string", "Optional search query within the section", required=False),
                ToolParameter("limit", "integer", "Maximum number of results to return", required=False, default=10),
            ],
            returns="List of chunks from the specified section type",
        ),
        ToolDefinition(
            name="search_speaker",
            description="Search for content related to a specific speaker or participant in the meeting.",
            category=ToolCategory.SEARCH,
            parameters=[
                ToolParameter("speaker_query", "string", "Speaker name or role to search for"),
                ToolParameter("limit", "integer", "Maximum number of results to return", required=False, default=10),
            ],
            returns="List of chunks related to the specified speaker",
        ),
        ToolDefinition(
            name="get_summary",
            description="Retrieve the meeting summary sections. Returns executive summary, detailed summary, and/or key points.",
            category=ToolCategory.RETRIEVAL,
            parameters=[
                ToolParameter("summary_type", "string", "Type of summary to retrieve", required=False, default="all", enum=["executive", "topic", "timeline", "all"]),
            ],
            returns="Summary sections of the meeting",
        ),
        ToolDefinition(
            name="get_action_items",
            description="Retrieve action items and follow-up tasks identified in the meeting.",
            category=ToolCategory.RETRIEVAL,
            parameters=[],
            returns="Action items and follow-ups from the meeting",
        ),
        ToolDefinition(
            name="get_decisions",
            description="Retrieve decisions and outcomes made during the meeting.",
            category=ToolCategory.RETRIEVAL,
            parameters=[],
            returns="Decisions and outcomes from the meeting",
        ),
        ToolDefinition(
            name="get_risks",
            description="Retrieve risks, blockers, and open questions identified in the meeting.",
            category=ToolCategory.RETRIEVAL,
            parameters=[],
            returns="Risks, blockers, and open questions from the meeting",
        ),
        ToolDefinition(
            name="get_timeline",
            description="Retrieve event timeline and deadline information from the meeting.",
            category=ToolCategory.RETRIEVAL,
            parameters=[],
            returns="Timeline and deadline information from the meeting",
        ),
        ToolDefinition(
            name="get_participants",
            description="Retrieve participant and speaker information including names, roles, counts, overview, and participant-related facts such as nationality, citizenship, age, education, or contact details.",
            category=ToolCategory.RETRIEVAL,
            parameters=[],
            returns="Participant details from the meeting",
        ),
    ]
