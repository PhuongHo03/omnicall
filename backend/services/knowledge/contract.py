"""Runtime contract for the generalized knowledge record envelope."""

from collections.abc import Mapping
from typing import Final

from backend.services.knowledge.semantic_registry import canonical_record_type


KNOWLEDGE_SCHEMA_VERSION: Final = "meeting-intelligence-result.v2"
RECORD_REQUIRED_KEYS: Final = frozenset(
    {"id", "type", "subtype", "data", "scope", "evidenceRefs", "sourceRefs", "derivedFrom", "confidence", "status"}
)
_CANONICAL_TYPES: Final = frozenset(
    {"participant", "entity", "fact", "event", "topic", "action", "decision", "risk", "question", "relationship", "observation"}
)


def build_record(
    *,
    record_id: str,
    record_type: object,
    data: Mapping[str, object] | None = None,
    subtype: str | None = None,
    scope: str = "meeting",
    evidence_refs: list[str] | None = None,
    source_refs: list[str] | None = None,
    derived_from: list[str] | None = None,
    confidence: float = 0.5,
    status: str = "candidate",
) -> dict:
    """Build one normalized record without arbitrary top-level schema keys."""

    payload = dict(data or {})
    canonical_type = canonical_record_type(record_type, data=payload)
    normalized_subtype = subtype or _subtype(payload, record_type)
    return {
        "id": record_id,
        "type": canonical_type,
        "subtype": normalized_subtype,
        "data": payload,
        "scope": scope,
        "evidenceRefs": _unique_strings(evidence_refs),
        "sourceRefs": _unique_strings(source_refs),
        "derivedFrom": _unique_strings(derived_from),
        "confidence": max(0.0, min(1.0, float(confidence))),
        "status": status,
    }


def validate_record_shape(record: object) -> None:
    if not isinstance(record, dict):
        raise ValueError("Knowledge records must be objects.")
    missing = RECORD_REQUIRED_KEYS.difference(record)
    if missing:
        raise ValueError(f"Knowledge record is missing fields: {', '.join(sorted(missing))}")
    if not isinstance(record["id"], str) or not record["id"]:
        raise ValueError("Knowledge record id must be a non-empty string.")
    if record["type"] not in _CANONICAL_TYPES:
        raise ValueError(f"Knowledge record has an unregistered type: {record['type']}")
    if not isinstance(record["subtype"], str) or not record["subtype"]:
        raise ValueError(f"Knowledge record subtype must be non-empty: {record['id']}")
    if not isinstance(record["data"], dict):
        raise ValueError(f"Knowledge record data must be an object: {record['id']}")
    for field in ("evidenceRefs", "sourceRefs", "derivedFrom"):
        if not isinstance(record[field], list) or not all(isinstance(value, str) for value in record[field]):
            raise ValueError(f"Knowledge record {field} must be a list of strings: {record['id']}")
    if not isinstance(record["confidence"], int | float) or not 0 <= float(record["confidence"]) <= 1:
        raise ValueError(f"Knowledge record confidence must be between 0 and 1: {record['id']}")


def _subtype(payload: Mapping[str, object], raw_type: object) -> str:
    candidate = payload.get("subtype") or payload.get("type")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    if isinstance(raw_type, str) and raw_type.strip():
        return raw_type.strip()
    return "unclassified"


def _unique_strings(values: list[str] | None) -> list[str]:
    return list(dict.fromkeys(value for value in (values or []) if isinstance(value, str) and value))
