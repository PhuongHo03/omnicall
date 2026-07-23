"""Deterministic retrieval planning and EvidenceBundle construction."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from backend.repositories.retrieval_repository import MeetingChunkRepository
from backend.services.retrieval.search_service import RetrievalSearchService
from backend.services.simple_rag.contracts import EvidenceBundle, EvidenceRef, GoalSpec, QuerySpec, TranscriptExcerpt, TypedFact


_SECTIONS = {
    "participant": ("fact.participant_count", "participant.overview", "participant.profile", "speaker.stats"),
    "contact": ("participant.profile", "entity.profile", "fact.record"),
    "entity": ("entity.profile", "participant.profile", "fact.record"),
    "action": ("action.item",),
    "decision": ("decision.record",),
    "risk": ("risk.record",),
    "date": ("meeting.metadata", "event.timeline", "fact.record"),
    "location": ("meeting.metadata", "fact.record", "event.timeline"),
}


class EvidenceRetrievalService:
    def __init__(self, session: Session, search: RetrievalSearchService | None = None) -> None:
        self.repository = MeetingChunkRepository(session)
        self.search = search or RetrievalSearchService(session)

    def retrieve(self, meeting_id: str, query: QuerySpec) -> tuple[EvidenceBundle, ...]:
        generation = self.repository.current_index_generation(meeting_id)
        if not generation:
            return tuple(
                EvidenceBundle(goal.goal_id, meeting_id, "unavailable", "insufficient", missing_fields=goal.requested_fields)
                for goal in query.goals
            )
        records = self.repository.list_for_meeting(meeting_id)
        bundles: list[EvidenceBundle] = []
        for goal in query.goals:
            selected = self._structured(records, goal)
            if not selected and goal.operation != "direct":
                selected = [item.record for item in self.search.search_meeting(meeting_id=meeting_id, query=query.question, limit=6)]
            bundles.append(self._bundle(meeting_id, generation, goal, selected))
        return tuple(bundles)

    def plan(self, query: QuerySpec) -> list[dict]:
        return [
            {
                "goalId": goal.goal_id,
                "strategy": "none" if goal.operation == "direct" else "structured_then_semantic",
                "sectionTypes": list(self._sections(goal)),
            }
            for goal in query.goals
        ]

    def current_generation(self, meeting_id: str) -> str | None:
        """Read the ready snapshot again at the terminal verification boundary."""
        return self.repository.current_index_generation(meeting_id)

    def _structured(self, records, goal: GoalSpec):
        sections = self._sections(goal)
        if goal.operation == "direct":
            return []
        candidates = [record for record in records if record.section_type in sections]
        if goal.entities:
            terms = {term.casefold() for entity in goal.entities for term in entity.split() if len(term) > 1}
            candidates = [record for record in candidates if terms & set(record.text.casefold().split())]
        return sorted(candidates, key=lambda item: (sections.index(item.section_type), item.chunk_id))[:8]

    def _sections(self, goal: GoalSpec) -> tuple[str, ...]:
        if goal.operation == "summarize":
            # A whole-meeting answer must be based on a whole-meeting summary
            # or, when none is verified, on transcript evidence.  Individual
            # extracted records are not a safe substitute: a bad local
            # extraction can turn one alleged fact into the topic of the
            # entire meeting.
            return ("summary.executive", "summary.topic", "topic.summary", "transcript.window")
        return _SECTIONS.get(goal.target, ("fact.record", "transcript.window"))

    def _bundle(self, meeting_id: str, generation: str, goal: GoalSpec, records) -> EvidenceBundle:
        refs: list[EvidenceRef] = []
        facts: list[TypedFact] = []
        excerpts: list[TranscriptExcerpt] = []
        seen_refs: set[str] = set()
        for record in records:
            metadata = record.metadata_json if isinstance(record.metadata_json, dict) else {}
            if metadata.get("indexGeneration") not in (None, generation):
                continue
            locations = metadata.get("citationLocations") if isinstance(metadata.get("citationLocations"), dict) else {}
            ref_limit = 4 if goal.answer_shape == "scalar" else 12
            valid_refs = tuple(
                ref
                for ref in record.citation_ids
                if isinstance(ref, str)
                and ref
                and ref not in seen_refs
                and isinstance(locations.get(ref), dict)
                and bool(locations[ref].get("segmentIds"))
            )[:ref_limit]
            seen_refs.update(valid_refs)
            for ref in valid_refs:
                location = locations[ref]
                refs.append(EvidenceRef(
                    ref,
                    record.chunk_id,
                    tuple(location.get("segmentIds") or ()),
                    location.get("startMs"),
                    location.get("endMs"),
                ))
            if not valid_refs:
                continue
            field, value, value_type = _typed_value(record)
            facts.append(TypedFact(f"fact:{record.chunk_id}", field, value, value_type, "complete", valid_refs))
            excerpts.append(TranscriptExcerpt(record.chunk_id, tuple(record.segment_ids or ()), record.start_ms, record.end_ms, record.text[:1200], valid_refs))
            if goal.answer_shape == "scalar" and value_type == "number":
                break
        status = "sufficient" if facts else "insufficient"
        return EvidenceBundle(
            goal.goal_id,
            meeting_id,
            generation,
            status,
            tuple(facts),
            tuple(excerpts),
            tuple(refs),
            () if facts else goal.requested_fields,
        )


def _typed_value(record) -> tuple[str, object, str]:
    metadata = record.metadata_json if isinstance(record.metadata_json, dict) else {}
    if record.section_type == "transcript.window":
        # The indexed chunk includes indexing labels/timestamps for search, but
        # those are prompt noise.  The synthesis contract receives only the
        # cited spoken text, so a whole-meeting fallback remains both grounded
        # and small enough for the configured local model.
        quotes = metadata.get("citationQuotes")
        if isinstance(quotes, dict):
            spoken = " ".join(
                str(quotes[ref]).strip()
                for ref in record.citation_ids
                if isinstance(quotes.get(ref), str) and quotes[ref].strip()
            )
            if spoken:
                return "transcript.window", spoken, "text"
    fields = metadata.get("recordFields") if isinstance(metadata.get("recordFields"), dict) else {}
    for key in ("value", "participantCount", "count", "email", "phone", "name", "date", "location"):
        for source in (fields, metadata):
            if key not in source or source[key] in (None, ""):
                continue
            value = source[key]
            if isinstance(value, list):
                return key, value, "list"
            if key == "email":
                return key, value, "email"
            if key == "phone":
                return key, value, "phone"
            if key == "date":
                return key, value, "date"
            return key, value, "number" if isinstance(value, (int, float)) else "string"
    count_match = re.search(r"(?:participantCount|participant count|số người)[^0-9]{0,12}(\d+)", record.text, re.IGNORECASE)
    if count_match:
        return "count", int(count_match.group(1)), "number"
    return record.section_type, record.text.strip(), "text"
