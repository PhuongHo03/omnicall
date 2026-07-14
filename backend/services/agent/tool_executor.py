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
    SECTION_PARTICIPANT_COUNT = "fact.participant_count"
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

    def search_records(self, *, meeting_id: str, arguments: dict[str, Any]) -> ToolExecutionResult:
        record_type = arguments.get("record_type") or arguments.get("recordType")
        record_types = arguments.get("record_types") or arguments.get("recordTypes") or ([] if not record_type else [record_type])
        record_types = [str(item) for item in record_types if item]
        subtype = arguments.get("subtype") or arguments.get("record_subtype")
        subtypes = arguments.get("record_subtypes") or arguments.get("recordSubtypes") or ([] if not subtype else [subtype])
        subtypes = [str(item) for item in subtypes if item]
        relation_types = arguments.get("relation_types") or arguments.get("relationTypes") or []
        relation_types = [str(item) for item in relation_types if item]
        answer_shape = str(arguments.get("answer_shape") or arguments.get("answerShape") or "record_list")
        query = str(arguments.get("query") or "").lower().strip()
        limit = max(1, min(int(arguments.get("limit", 10)), 50))
        records = []
        for chunk in self.chunks.list_for_meeting(meeting_id):
            metadata = chunk.metadata_json or {}
            if metadata.get("recordId") is None:
                continue
            if record_types and metadata.get("recordType") not in record_types:
                continue
            if subtypes and metadata.get("subtype") not in subtypes:
                continue
            if relation_types and not _matches_relations(metadata, relation_types):
                continue
            # A planner query is context for selecting record types, not an
            # exact sentence that must occur verbatim in the record payload.
            # Apply text matching only for unconstrained generic searches.
            if query and not record_types and not subtypes and query not in chunk.text.lower():
                continue
            records.append(chunk)
        records = _prioritize_record_shape(records, answer_shape)[:limit]
        return ToolExecutionResult(
            tool_name="search_records",
            success=True,
            data=[chunk_to_dict(chunk) for chunk in records],
            metadata={"recordTypes": record_types, "recordSubtypes": subtypes, "relationTypes": relation_types, "answerShape": answer_shape, "query": query or None, "resultCount": len(records)},
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


def _matches_relations(metadata: dict[str, Any], relation_types: list[str]) -> bool:
    fields = metadata.get("recordFields") or {}
    if not isinstance(fields, dict):
        return False
    relation_aliases = {
        "performed": ("actor", "actorId", "performedBy", "owner", "ownerParticipantId"),
        "actor": ("actor", "actorId", "performedBy", "owner", "ownerParticipantId"),
        "targets": ("target", "targetId", "targets", "entity", "entityId"),
        "located_at": ("location", "venue", "address", "target"),
    }
    return any(any(key in fields and fields[key] not in (None, "", []) for key in relation_aliases.get(relation, (relation,))) for relation in relation_types)


def _prioritize_record_shape(records: list[Any], answer_shape: str) -> list[Any]:
    if answer_shape == "participant_list":
        return sorted(records, key=lambda chunk: (str((chunk.metadata_json or {}).get("subtype")) != "speaker_profile", str((chunk.metadata_json or {}).get("recordId"))))
    if answer_shape in {"actor_target", "location"}:
        return sorted(records, key=lambda chunk: (not bool((chunk.metadata_json or {}).get("recordFields", {}).get("actor") or (chunk.metadata_json or {}).get("recordFields", {}).get("target")), str((chunk.metadata_json or {}).get("recordId"))))
    if answer_shape == "timeline":
        return sorted(records, key=lambda chunk: (chunk.start_ms is None, chunk.start_ms or 0, str((chunk.metadata_json or {}).get("recordId"))))
    return records
