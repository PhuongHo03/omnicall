"""Runtime implementations for the Agentic RAG retrieval tools."""

from typing import Any

from backend.repositories.retrieval_repository import MeetingChunkRepository
from backend.services.retrieval.search_service import RetrievalSearchService
from backend.services.agent.tool_definitions import ToolExecutionResult, chunk_to_dict
from backend.services.retrieval.section_registry import SECTION_TYPE_SET


class AgentToolExecutor:
    """Execute retrieval and synthesis tools against injected repositories."""

    SECTION_SUMMARY_EXECUTIVE = "summary.executive"
    SECTION_SUMMARY_TOPIC = "summary.topic"
    SECTION_SUMMARY_TIMELINE = "summary.timeline"
    SECTION_ACTION_ITEM = "action.item"
    SECTION_DECISION_RECORD = "decision.record"
    SECTION_RISK_RECORD = "risk.record"
    SECTION_EVENT_TIMELINE = "event.timeline"
    SECTION_PARTICIPANT_OVERVIEW = "participant.overview"
    SECTION_PARTICIPANT_PROFILE = "participant.profile"
    SECTION_FACT_RECORD = "fact.record"
    SECTION_ENTITY_PROFILE = "entity.profile"

    VALID_SECTION_TYPES = SECTION_TYPE_SET

    def __init__(
        self,
        chunks: MeetingChunkRepository,
        retrieval_search: RetrievalSearchService,
    ) -> None:
        self.chunks = chunks
        self.retrieval_search = retrieval_search

    def search_semantic(self, *, meeting_id: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        query = arguments.get("query")
        if not query:
            return self._missing("search_semantic", "query")
        results = self.retrieval_search.search_meeting(
            meeting_id=meeting_id,
            query=query,
            limit=arguments.get("limit", 6),
        )
        return ToolExecutionResult(
            tool_name="search_semantic",
            success=True,
            data=[{
                **chunk_to_dict(result.record if hasattr(result, "record") else result),
                "score": getattr(result, "score", 0.0),
            } for result in results],
            metadata={"query": query, "resultCount": len(results), "searchType": "semantic"},
        )

    def search_keyword(self, *, meeting_id: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        # The planner may provide a normalized synonym query alongside the
        # user's original wording. Prefer that query so keyword retrieval can
        # bridge Vietnamese questions to English canonical JSON chunks.
        keyword = arguments.get("query") or arguments.get("keyword")
        if not keyword:
            return self._missing("search_keyword", "keyword")
        results = self.chunks.search_by_keyword(
            meeting_id=meeting_id, keyword=keyword, limit=arguments.get("limit", 10)
        )
        return ToolExecutionResult(
            tool_name="search_keyword", success=True,
            data=[chunk_to_dict(chunk) for chunk in results],
            metadata={"keyword": keyword, "resultCount": len(results), "searchType": "keyword"},
        )

    def search_section(self, *, meeting_id: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        section_type = arguments.get("section_type")
        if not section_type:
            return self._missing("search_section", "section_type")
        if section_type not in self.VALID_SECTION_TYPES:
            return ToolExecutionResult(
                tool_name="search_section", success=False,
                error=f"Invalid section_type '{section_type}'. Valid types: {', '.join(sorted(self.VALID_SECTION_TYPES))}",
            )
        query = arguments.get("query")
        limit = arguments.get("limit", 10)
        results = self.chunks.list_by_section_type(
            meeting_id=meeting_id, section_type=section_type,
            limit=max(limit * 4, 20) if query else limit,
        )
        if query:
            terms = [term.lower() for term in query.replace("|", " ").replace("OR", " ").replace("or", " ").split() if term]
            results = [
                chunk for chunk in results
                if any(term in chunk.text.lower() for term in terms)
            ][:limit]
        return ToolExecutionResult(
            tool_name="search_section", success=True,
            data=[chunk_to_dict(chunk) for chunk in results],
            metadata={"sectionType": section_type, "query": query, "resultCount": len(results), "searchType": "section"},
        )

    def search_speaker(self, *, meeting_id: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        speaker_query = arguments.get("speaker_query")
        if not speaker_query:
            return self._missing("search_speaker", "speaker_query")
        results = self.chunks.search_by_speaker(
            meeting_id=meeting_id, query=speaker_query, limit=arguments.get("limit", 10)
        )
        return ToolExecutionResult(
            tool_name="search_speaker", success=True,
            data=[chunk_to_dict(chunk) for chunk in results],
            metadata={"speakerQuery": speaker_query, "resultCount": len(results), "searchType": "speaker"},
        )

    def get_summary(self, *, meeting_id: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        summary_type = arguments.get("summary_type", "all")
        if summary_type == "executive":
            section_types = [self.SECTION_SUMMARY_EXECUTIVE]
        elif summary_type == "topic":
            section_types = [self.SECTION_SUMMARY_TOPIC, "topic.summary"]
        elif summary_type == "timeline":
            section_types = [self.SECTION_SUMMARY_TIMELINE, self.SECTION_EVENT_TIMELINE]
        else:
            section_types = [self.SECTION_SUMMARY_EXECUTIVE, self.SECTION_SUMMARY_TOPIC, self.SECTION_SUMMARY_TIMELINE, "topic.summary"]
        results = self.chunks.get_structured_sections(meeting_id=meeting_id, section_types=section_types)
        return self._sections("get_summary", results, {"summaryType": summary_type, "sectionTypes": section_types})

    def get_action_items(self, *, meeting_id: str) -> ToolExecutionResult:
        return self._section_tool("get_action_items", meeting_id, [self.SECTION_ACTION_ITEM, "question.record"], [self.SECTION_ACTION_ITEM], ["question.record"])

    def get_decisions(self, *, meeting_id: str) -> ToolExecutionResult:
        return self._section_tool("get_decisions", meeting_id, [self.SECTION_DECISION_RECORD, self.SECTION_EVENT_TIMELINE], [self.SECTION_DECISION_RECORD], [self.SECTION_EVENT_TIMELINE])

    def get_risks(self, *, meeting_id: str) -> ToolExecutionResult:
        return self._section_tool("get_risks", meeting_id, [self.SECTION_RISK_RECORD, "question.record"], [self.SECTION_RISK_RECORD], ["question.record"])

    def get_timeline(self, *, meeting_id: str) -> ToolExecutionResult:
        return self._section_tool("get_timeline", meeting_id, [self.SECTION_EVENT_TIMELINE, self.SECTION_SUMMARY_TIMELINE])

    def get_participants(self, *, meeting_id: str) -> ToolExecutionResult:
        return self._section_tool("get_participants", meeting_id, ["speaker.stats", self.SECTION_PARTICIPANT_OVERVIEW, self.SECTION_PARTICIPANT_PROFILE, self.SECTION_FACT_RECORD, self.SECTION_ENTITY_PROFILE], ["speaker.stats", self.SECTION_PARTICIPANT_OVERVIEW, self.SECTION_PARTICIPANT_PROFILE], [self.SECTION_FACT_RECORD, self.SECTION_ENTITY_PROFILE])

    def _section_tool(self, tool_name: str, meeting_id: str, section_types: list[str], primary_sections: list[str] | None = None, fallback_sections: list[str] | None = None) -> ToolExecutionResult:
        results = self.chunks.get_structured_sections(meeting_id=meeting_id, section_types=section_types)
        return self._sections(tool_name, results, {
            "primarySections": primary_sections or section_types,
            "fallbackSections": fallback_sections or [],
        })

    @staticmethod
    def _sections(tool_name: str, results: list[Any], metadata: dict[str, Any]) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_name=tool_name, success=True,
            data=[chunk_to_dict(chunk) for chunk in results],
            metadata={**metadata, "resultCount": len(results)},
        )

    @staticmethod
    def _missing(tool_name: str, parameter: str) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_name=tool_name, success=False,
            error=f"Missing required parameter: '{parameter}'",
        )
