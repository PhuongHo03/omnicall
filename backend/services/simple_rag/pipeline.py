"""Linear Request -> Evidence -> Synthesis -> Verification pipeline."""

from __future__ import annotations

import time
from typing import Any, Callable, Iterable

from sqlalchemy.orm import Session

from backend.configs.settings import Settings, get_settings
from backend.models.meeting_models import ChatMessage
from backend.providers.llm import FallbackLLMProviderError, LLMProvider, LLMProviderError, get_llm_provider
from backend.services.simple_rag.answer_synthesis_service import AnswerSynthesisService, SynthesisContractError
from backend.services.simple_rag.contracts import PIPELINE_CONTRACT_VERSION, PipelineResult, SynthesisContract
from backend.services.simple_rag.evidence_retrieval_service import EvidenceRetrievalService
from backend.services.simple_rag.query_interpretation_service import QueryInterpretationService


_FIXED = {
    "vi": {
        "clarification": "Bạn vui lòng nói rõ đối tượng hoặc thông tin cần tìm.",
        "not_enough_evidence": "Không có đủ bằng chứng đã được xác minh để trả lời câu hỏi này.",
        "error": "Không thể tạo câu trả lời đã được xác minh lúc này. Vui lòng thử lại sau.",
    },
    "en": {
        "clarification": "Please clarify the subject or information you want to find.",
        "not_enough_evidence": "There is not enough verified evidence to answer this question.",
        "error": "A verified answer could not be generated right now. Please try again later.",
    },
}


class SimpleRAGPipeline:
    def __init__(self, session: Session, *, llm_provider: LLMProvider | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.interpreter = QueryInterpretationService(self.settings)
        self.retrieval = EvidenceRetrievalService(session)
        self.synthesis = AnswerSynthesisService(llm_provider or get_llm_provider(), self.settings)

    def run(self, *, meeting_id: str, question: str, history: Iterable[ChatMessage] = (), language_hint: str | None = None, deadline_monotonic: float | None = None, stage_callback: Callable[[str], None] | None = None) -> PipelineResult:
        started = time.monotonic()
        deadline = deadline_monotonic or (started + self.settings.rag_chat_turn_timeout_seconds)
        trace: list[dict[str, Any]] = [_stage("request_gate", 0, "succeeded", {})]

        _notify(stage_callback, "query_interpretation")
        query, duration = _timed(self.interpreter.interpret, question, history, language_hint=language_hint)
        if duration > self.settings.rag_query_interpretation_timeout_seconds * 1000:
            raise TimeoutError("rag_query_interpretation_timeout")
        trace.append(_stage("query_interpretation", duration, "succeeded", {"querySpec": query.to_dict()}))
        language = query.language
        if query.clarification_reason:
            trace.append(_stage("retrieval", 0, "skipped", {"reason": "clarification_needed"}))
            return self._fixed(_FIXED[language]["clarification"], "clarification_needed", "clarification_needed", trace)

        _notify(stage_callback, "retrieval")
        plans = self.retrieval.plan(query)
        bundles, duration = _timed(self.retrieval.retrieve, meeting_id, query)
        if duration > self.settings.rag_evidence_retrieval_timeout_seconds * 1000:
            raise TimeoutError("rag_evidence_retrieval_timeout")
        trace.append(_stage("retrieval", duration, "succeeded", {"plan": plans, "bundleCount": len(bundles)}))
        _notify(stage_callback, "evidence_validation")
        invalid = any(bundle.meeting_id != meeting_id or not bundle.snapshot_generation for bundle in bundles)
        trace.append(_stage("evidence_validation", 0, "failed" if invalid else "succeeded", {
            "bundles": [bundle.to_dict(include_quotes=False) for bundle in bundles],
        }))
        direct = bool(query.goals and query.goals[0].operation == "direct")
        if invalid or (not direct and (not bundles or any(bundle.status == "insufficient" for bundle in bundles))):
            return self._fixed(_FIXED[language]["not_enough_evidence"], "not_enough_evidence", "completed", trace)

        facts = tuple(fact for bundle in bundles for fact in bundle.typed_facts)
        refs = tuple(dict.fromkeys(ref.ref_id for bundle in bundles for ref in bundle.refs))
        contract = SynthesisContract(
            language=language,
            answer_style="natural, concise, complete",
            goals=query.goals,
            bundles=bundles,
            locked_facts=facts,
            allowed_refs=refs,
            direct_intent=query.goals[0].target if direct else None,
            disclosure_permissions=tuple(field for goal in query.goals for field in goal.requested_fields),
        )
        _notify(stage_callback, "synthesis")
        synthesis_started = time.perf_counter()
        synthesis_budget = deadline - time.monotonic() - self.settings.rag_finalization_reserve_seconds
        if synthesis_budget <= 0:
            raise TimeoutError("rag_finalization_reserve_exhausted")
        synthesis_budget = min(
            synthesis_budget,
            self.settings.rag_synthesis_primary_timeout_seconds + self.settings.rag_synthesis_fallback_timeout_seconds,
        )
        try:
            payload, verification, provider, attempts = self.synthesis.synthesize(
                contract,
                total_timeout_seconds=synthesis_budget,
            )
        except SynthesisContractError as exc:
            synthesis_duration = round((time.perf_counter() - synthesis_started) * 1000)
            trace.append(_stage("synthesis", synthesis_duration, "failed", {
                "reason": "synthesis_contract_invalid",
                "attempts": self.settings.rag_synthesis_contract_retries + 1,
            }))
            trace.append(_stage("answer_verification", 0, "failed", {
                "contractVersion": exc.verification.version,
                "errors": list(exc.verification.errors),
            }))
            trace.append(_stage("output_policy", 0, "succeeded", {"fixedControlResponse": True}))
            return PipelineResult(
                _FIXED[language]["error"],
                "error",
                "control",
                pipeline_trace={"version": 1, "contract": PIPELINE_CONTRACT_VERSION, "stages": trace},
                terminal_status="error",
            )
        except (FallbackLLMProviderError, LLMProviderError) as exc:
            # A transport/provider failure is already terminal for this chat
            # turn.  Retrying the Celery task reruns retrieval and can create
            # duplicate user-visible failures without making the provider
            # healthy.  Preserve bounded provider provenance in the trace and
            # return the fixed control response required by the contract.
            synthesis_duration = round((time.perf_counter() - synthesis_started) * 1000)
            details = {"reason": "provider_failure", "errorType": type(exc).__name__}
            if isinstance(exc, FallbackLLMProviderError):
                details.update({
                    "primaryProvider": exc.primary_provider,
                    "primaryModel": exc.primary_model,
                    "fallbackProvider": exc.fallback_provider,
                    "fallbackModel": exc.fallback_model,
                })
            trace.append(_stage("synthesis", synthesis_duration, "failed", details))
            trace.append(_stage("answer_verification", 0, "skipped", {"reason": "provider_failure"}))
            trace.append(_stage("output_policy", 0, "succeeded", {"fixedControlResponse": True}))
            return PipelineResult(
                _FIXED[language]["error"],
                "error",
                "control",
                pipeline_trace={"version": 1, "contract": PIPELINE_CONTRACT_VERSION, "stages": trace},
                terminal_status="error",
            )
        synthesis_duration = round((time.perf_counter() - synthesis_started) * 1000)
        trace.append(_stage("synthesis", synthesis_duration, "succeeded", {"attempts": attempts}, provider.provider_name, provider.model_name))
        _notify(stage_callback, "answer_verification")
        current_generation = self.retrieval.current_generation(meeting_id)
        expected_generations = {bundle.snapshot_generation for bundle in bundles}
        if current_generation is None or expected_generations != {current_generation}:
            raise RuntimeError("retrieval_snapshot_changed")
        trace.append(_stage("answer_verification", 0, "succeeded", {
            "contractVersion": verification.version,
            "snapshotGeneration": current_generation,
            "verifiedRefs": list(verification.verified_refs),
        }))
        citations, chunk_ids = _citations(bundles, verification.verified_refs)
        trace.append(_stage("output_policy", 0, "succeeded", {"citationCount": len(citations)}))
        if time.monotonic() >= deadline:
            raise TimeoutError("rag_chat_turn_timeout")
        return PipelineResult(
            answer=payload["answer"].strip(),
            evidence_state="grounded" if not direct else "direct",
            answer_origin_kind="llm_synthesis",
            citations=tuple(citations),
            retrieved_chunk_ids=tuple(chunk_ids),
            provider=provider.provider_name,
            model=provider.model_name,
            pipeline_trace={"version": 1, "contract": PIPELINE_CONTRACT_VERSION, "stages": trace},
        )

    def _fixed(self, answer: str, state: str, terminal: str, trace: list[dict[str, Any]]) -> PipelineResult:
        trace.append(_stage("synthesis", 0, "skipped", {"reason": state}))
        trace.append(_stage("answer_verification", 0, "skipped", {"reason": state}))
        trace.append(_stage("output_policy", 0, "succeeded", {"fixedControlResponse": True}))
        return PipelineResult(answer, state, "control", pipeline_trace={"version": 1, "contract": PIPELINE_CONTRACT_VERSION, "stages": trace}, terminal_status=terminal)


def _timed(function, *args, **kwargs):
    started = time.perf_counter()
    return function(*args, **kwargs), round((time.perf_counter() - started) * 1000)


def _notify(callback: Callable[[str], None] | None, stage: str) -> None:
    if callback is not None:
        callback(stage)


def _stage(name: str, duration_ms: int, status: str, details: dict[str, Any], provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    return {"stage": name, "status": status, "durationMs": duration_ms, "provider": provider, "model": model, "details": details}


def _citations(bundles, verified_refs):
    verified = set(verified_refs)
    citations: list[dict[str, Any]] = []
    chunks: list[str] = []
    for bundle in bundles:
        excerpt_by_chunk = {item.chunk_id: item for item in bundle.transcript_excerpts}
        for ref in bundle.refs:
            if ref.ref_id not in verified:
                continue
            excerpt = excerpt_by_chunk.get(ref.chunk_id)
            citations.append({
                "citation_id": ref.ref_id,
                "chunk_id": ref.chunk_id,
                "source_type": "meeting-intelligence",
                "section_type": next((fact.field for fact in bundle.typed_facts if ref.ref_id in fact.refs), "evidence"),
                "json_pointer": "",
                "segment_ids": list(ref.segment_ids),
                "start_ms": ref.start_ms,
                "end_ms": ref.end_ms,
                "quote": excerpt.quote[:500] if excerpt else "",
            })
            chunks.append(ref.chunk_id)
    return citations, list(dict.fromkeys(chunks))
