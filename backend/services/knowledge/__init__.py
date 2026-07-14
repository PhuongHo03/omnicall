"""Knowledge-domain contracts and semantic normalization helpers."""

from backend.services.knowledge.semantic_registry import (
    CANONICAL_RECORD_TYPES,
    canonical_record_type,
    record_type_definition,
)
from backend.services.knowledge.contract import KNOWLEDGE_SCHEMA_VERSION, build_record, validate_record_shape
from backend.services.knowledge.evidence import build_evidence_item, evidence_by_id, evidence_items
from backend.services.knowledge.normalization import normalize_candidate

__all__ = [
    "CANONICAL_RECORD_TYPES",
    "KNOWLEDGE_SCHEMA_VERSION",
    "build_record",
    "build_evidence_item",
    "canonical_record_type",
    "evidence_by_id",
    "evidence_items",
    "normalize_candidate",
    "record_type_definition",
    "validate_record_shape",
]
