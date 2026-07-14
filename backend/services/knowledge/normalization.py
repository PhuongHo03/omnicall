"""Normalize provider/window candidates into the v2 knowledge envelope."""

from backend.services.knowledge.contract import build_record


SECTION_TO_TYPE = {
    "participants": "participant",
    "entities": "entity",
    "facts": "fact",
    "events": "event",
    "topics": "topic",
    "actions": "action",
    "decisions": "decision",
    "risks": "risk",
    "questions": "question",
    "relationships": "relationship",
}


def normalize_candidate(
    *,
    item: dict,
    section: str,
    record_id: str,
    source_ref: str,
    evidence_refs: list[str],
) -> dict:
    """Convert a provider candidate while preserving unknown fields in data."""

    payload = dict(item)
    payload.pop("id", None)
    payload.pop("citationIds", None)
    payload.pop("sourceWindowIds", None)
    raw_type = item.get("recordType") or SECTION_TO_TYPE.get(section) or section
    subtype = item.get("subtype") or item.get("type")
    derived = item.get("derivedFrom")
    derived_from = derived if isinstance(derived, list) else [derived] if isinstance(derived, str) else []
    return build_record(
        record_id=record_id,
        record_type=raw_type,
        subtype=subtype if isinstance(subtype, str) else None,
        data=payload,
        evidence_refs=evidence_refs,
        source_refs=[source_ref],
        derived_from=derived_from,
        confidence=float(item.get("confidence", 0.5) or 0.5),
        status="candidate",
    )
