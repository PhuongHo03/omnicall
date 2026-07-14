"""Deterministic evidence sufficiency checks for Agentic RAG."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.services.agent.context_manager import ContextChunk
from backend.services.agent.query_planner import QueryPlan


@dataclass(frozen=True)
class EvidenceVerificationResult:
    sufficient: bool
    missing_fields: list[str] = field(default_factory=list)
    matched_sections: list[str] = field(default_factory=list)
    evidence_chunk_ids: list[str] = field(default_factory=list)
    matched_record_types: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    matched_relations: list[str] = field(default_factory=list)
    missing_relations: list[str] = field(default_factory=list)
    reason_code: str = "no_evidence"

    def to_dict(self) -> dict[str, Any]:
        return {
            "sufficient": self.sufficient,
            "missingFields": self.missing_fields,
            "matchedSections": self.matched_sections,
            "evidenceChunkIds": self.evidence_chunk_ids,
            "matchedRecordTypes": self.matched_record_types,
            "evidenceRefs": self.evidence_refs,
            "matchedRelations": self.matched_relations,
            "missingRelations": self.missing_relations,
            "reasonCode": self.reason_code,
        }


def verify_evidence(plan: QueryPlan, chunks: list[ContextChunk]) -> EvidenceVerificationResult:
    if not chunks:
        return EvidenceVerificationResult(
            sufficient=False,
            missing_fields=list(plan.required_fields),
            reason_code="no_evidence",
        )

    matched_sections = sorted({chunk.section_type for chunk in chunks if chunk.section_type})
    matched_record_types = {str(chunk.metadata.get("recordType")) for chunk in chunks if chunk.metadata.get("recordType")}
    evidence_ids = [chunk.chunk_id for chunk in chunks]
    evidence_refs = list(dict.fromkeys(ref for chunk in chunks for ref in chunk.evidence_refs))
    text = " ".join(chunk.text.lower() for chunk in chunks)
    missing: list[str] = []
    for field in plan.required_fields:
        if not _field_present(field, text, chunks):
            missing.append(field)
    # v2 relevance is defined by canonical record selectors. Section labels are
    # retained only for top-level summary/metadata projections.
    relevant = bool(matched_record_types.intersection(plan.record_types)) if plan.record_types else False
    if not relevant:
        relevant = bool(set(matched_sections).intersection(plan.sections))
    if not relevant:
        missing = missing or ["relevant_section"]
    matched_relations = [relation for relation in plan.relation_types if _relation_present(relation, chunks)]
    missing_relations = [relation for relation in plan.relation_types if relation not in matched_relations]
    if missing_relations:
        missing.extend(f"relation:{relation}" for relation in missing_relations)
    sufficient = relevant and not missing
    return EvidenceVerificationResult(
        sufficient=sufficient,
        missing_fields=missing,
        matched_sections=matched_sections,
        evidence_chunk_ids=evidence_ids,
        matched_record_types=sorted(matched_record_types),
        evidence_refs=evidence_refs,
        matched_relations=matched_relations,
        missing_relations=missing_relations,
        reason_code="sufficient" if sufficient else "missing_required_evidence",
    )


def verify_answer_coverage(answer: str, chunks: list[ContextChunk], citations: list[str] | None = None) -> dict[str, Any]:
    """Validate final-answer references against the accumulated evidence."""
    known_citations = {citation for chunk in chunks for citation in chunk.citation_ids}
    requested = [item for item in (citations or []) if isinstance(item, str)]
    unknown = sorted(set(requested) - known_citations)
    return {
        "answerPresent": bool(isinstance(answer, str) and answer.strip()),
        "knownCitationCount": len(known_citations),
        "requestedCitationCount": len(requested),
        "unknownCitations": unknown,
        "valid": bool(isinstance(answer, str) and answer.strip()) and not unknown,
    }


def _field_present(field: str, text: str, chunks: list[ContextChunk]) -> bool:
    if field == "text":
        return bool(text.strip())
    aliases = {
        "displayName": ("display name", "name", "participant", "speaker"),
        "owner": ("owner", "assignee", "phu trach", "nguoi phu trach"),
        "dueDate": ("due", "deadline", "due date", "han", "deadline"),
        "status": ("status", "open", "closed", "completed", "confirmed"),
        "value": ("value", "participant count", "speaker count", "count", "price", "cost", "amount", "dollar", "$", "nationality", "citizenship", "quoc tich", "tuoi"),
        "predicate": ("predicate", "type", "fact"),
        "subject": ("subject", "participant", "speaker"),
        "severity": ("severity", "high", "medium", "low"),
        "warnings": ("warning", "warnings", "canh bao"),
        "coverage": ("coverage", "covered", "coverage"),
        "unsupportedClaims": ("unsupported", "unsupported claims"),
        "provider": ("provider", "analysis provider", "llm provider"),
        "model": ("model", "analysis model", "llm model"),
        "generatedAt": ("generated", "created", "timestamp"),
        "startMs": ("start", "start ms", "occurred"),
        "endMs": ("end", "end ms"),
    }
    # Generic records keep their payload and subtype in metadata; field
    # matching must inspect those values instead of depending on a section
    # name created for one particular LLM extraction.
    for chunk in chunks:
        metadata = chunk.metadata or {}
        if field in metadata or field in metadata.get("recordFields", {}):
            return True
    if any(alias in text for alias in aliases.get(field, (field.lower(),))):
        return True
    return any(field in str(chunk.metadata).lower() for chunk in chunks)


def _relation_present(relation: str, chunks: list[ContextChunk]) -> bool:
    aliases = {
        "performed": ("actor", "actorId", "performedBy", "owner", "ownerParticipantId"),
        "actor": ("actor", "actorId", "performedBy", "owner", "ownerParticipantId"),
        "targets": ("target", "targetId", "targets", "entity", "entityId"),
        "located_at": ("location", "venue", "address", "target"),
    }.get(relation, (relation,))
    return any(
        any(key in (chunk.metadata.get("recordFields") or {}) for key in aliases)
        for chunk in chunks
    )
