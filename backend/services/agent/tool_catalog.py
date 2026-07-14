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
            name="search_records",
            description="Search canonical knowledge records by registered type and optional subtype. Use this generic tool for facts, events, participants, observations, and any future subtype without adding a new tool.",
            category=ToolCategory.RETRIEVAL,
            parameters=[
                ToolParameter("record_type", "string", "Canonical record type such as fact, event, participant, or observation", required=False),
                ToolParameter("record_types", "array", "Canonical record types to include", required=False),
                ToolParameter("subtype", "string", "Optional record subtype such as participant_count or deadline", required=False),
                ToolParameter("record_subtypes", "array", "Record subtypes to include", required=False),
                ToolParameter("relation_types", "array", "Optional relationship capabilities such as performed, actor, targets, or located_at", required=False),
                ToolParameter("answer_shape", "string", "Expected projection shape such as record_list, participant_list, count, actor_target, location, or timeline", required=False),
                ToolParameter("query", "string", "Optional text to match within the record", required=False),
                ToolParameter("limit", "integer", "Maximum number of records to return", required=False, default=10),
            ],
            returns="Canonical knowledge records represented by retrieval chunks",
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
            name="get_summary",
            description="Retrieve the meeting summary sections. Returns executive summary, detailed summary, and/or key points.",
            category=ToolCategory.RETRIEVAL,
            parameters=[
                ToolParameter("summary_type", "string", "Type of summary to retrieve", required=False, default="all", enum=["executive", "topic", "timeline", "all"]),
            ],
            returns="Summary sections of the meeting",
        ),
    ]
