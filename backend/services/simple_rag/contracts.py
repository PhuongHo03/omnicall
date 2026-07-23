"""Immutable contracts for the only production chat pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


PIPELINE_CONTRACT_VERSION = "simple-rag.v1"
RETRIEVAL_CONTRACT_VERSION = "simple-retrieval.v1"
QUERY_SPEC_VERSION = "query-spec.v1"
EVIDENCE_BUNDLE_VERSION = "evidence-bundle.v1"
SYNTHESIS_CONTRACT_VERSION = "synthesis-contract.v1"
ANSWER_VERIFICATION_VERSION = "answer-verification.v1"


@dataclass(frozen=True)
class TrustedReference:
    message_id: str
    kind: Literal["target", "field", "entity"]
    value: str


@dataclass(frozen=True)
class GoalSpec:
    goal_id: str
    operation: str
    target: str
    requested_fields: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()
    filters: tuple[tuple[str, str], ...] = ()
    answer_shape: str = "paragraph"


@dataclass(frozen=True)
class QuerySpec:
    question: str
    language: Literal["vi", "en"]
    dependency_mode: Literal["standalone", "resolved", "ambiguous"]
    goals: tuple[GoalSpec, ...]
    trusted_history_anchors: tuple[TrustedReference, ...] = ()
    clarification_reason: str | None = None
    version: str = QUERY_SPEC_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRef:
    ref_id: str
    chunk_id: str
    segment_ids: tuple[str, ...]
    start_ms: int | None
    end_ms: int | None


@dataclass(frozen=True)
class TypedFact:
    fact_id: str
    field: str
    value: Any
    value_type: str
    completeness: Literal["complete", "partial", "unknown"]
    refs: tuple[str, ...]


@dataclass(frozen=True)
class TranscriptExcerpt:
    chunk_id: str
    segment_ids: tuple[str, ...]
    start_ms: int | None
    end_ms: int | None
    quote: str
    refs: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceBundle:
    goal_id: str
    meeting_id: str
    snapshot_generation: str
    status: Literal["sufficient", "partial", "insufficient"]
    typed_facts: tuple[TypedFact, ...] = ()
    transcript_excerpts: tuple[TranscriptExcerpt, ...] = ()
    refs: tuple[EvidenceRef, ...] = ()
    missing_fields: tuple[str, ...] = ()
    version: str = EVIDENCE_BUNDLE_VERSION

    def to_dict(self, *, include_quotes: bool = True) -> dict[str, Any]:
        value = asdict(self)
        if not include_quotes:
            for excerpt in value["transcript_excerpts"]:
                excerpt["quote"] = excerpt["quote"][:240]
        return value


@dataclass(frozen=True)
class SynthesisContract:
    language: str
    answer_style: str
    goals: tuple[GoalSpec, ...]
    bundles: tuple[EvidenceBundle, ...]
    locked_facts: tuple[TypedFact, ...]
    allowed_refs: tuple[str, ...]
    direct_intent: str | None = None
    disclosure_permissions: tuple[str, ...] = ()
    version: str = SYNTHESIS_CONTRACT_VERSION


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    errors: tuple[str, ...]
    verified_refs: tuple[str, ...]
    version: str = ANSWER_VERIFICATION_VERSION


@dataclass(frozen=True)
class PipelineResult:
    answer: str
    evidence_state: str
    answer_origin_kind: str
    citations: tuple[dict[str, Any], ...] = ()
    retrieved_chunk_ids: tuple[str, ...] = ()
    provider: str | None = None
    model: str | None = None
    pipeline_trace: dict[str, Any] = field(default_factory=dict)
    terminal_status: str = "completed"
