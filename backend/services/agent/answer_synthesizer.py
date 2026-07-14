"""Answer synthesis and retrieval fallback boundary for Agentic RAG."""

from __future__ import annotations

import time
import re
import unicodedata
from typing import Any

from backend.providers.llm import LLMProvider, LLMProviderError, get_effective_model_name, get_effective_provider_name
from backend.services.agent.context_manager import AgentContextManager
from backend.services.agent.context_coordinator import ContextCoordinator
from backend.services.agent.prompt_builder import synthesis_system_prompt, synthesis_user_prompt
from backend.services.agent.response_utils import (
    confidence,
    elapsed_ms,
    evidence_state,
    fallback_answer_from_context,
    normalize_chunk,
    to_context_chunk,
)
from backend.services.agent.evidence_verifier import verify_answer_coverage
from backend.services.agent.query_planner import build_query_plan
from backend.services.agent.result_models import AgentResult
from backend.services.retrieval.search_service import RetrievalSearchService


class AnswerSynthesizer:
    """Build final answers from agent decisions, context, or direct retrieval."""

    def __init__(
        self,
        *,
        llm_provider: LLMProvider,
        retrieval_search: RetrievalSearchService,
        context_manager: AgentContextManager,
        context_coordinator: ContextCoordinator,
    ) -> None:
        self.llm_provider = llm_provider
        self.retrieval_search = retrieval_search
        self.context_manager = context_manager
        self.context_coordinator = context_coordinator

    def from_decision(
        self,
        *,
        decision: dict[str, Any],
        thoughts: list[dict[str, Any]],
        started: float,
    ) -> AgentResult:
        answer = decision.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            return self.from_context(thoughts=thoughts, started=started)
        chunks = self.context_manager.get_chunks_sorted_by_score()
        requested_refs = decision.get("evidenceRefs") if isinstance(decision.get("evidenceRefs"), list) else []
        known_refs = {ref for chunk in chunks for ref in chunk.evidence_refs}
        verified_refs = list(dict.fromkeys(ref for ref in requested_refs if isinstance(ref, str) and ref in known_refs))
        requested_citations = decision.get("citations") if isinstance(decision.get("citations"), list) else []
        if verified_refs:
            requested_citations = list(dict.fromkeys(
                citation_id for chunk in chunks
                if set(chunk.evidence_refs).intersection(verified_refs)
                for citation_id in chunk.citation_ids
            ))
        citation_check = verify_answer_coverage(answer, chunks, requested_citations)
        return self._result(
            answer=answer.strip(),
            evidence_state=(evidence_state(decision.get("evidenceState"), has_context=bool(chunks)) if citation_check["valid"] else "partial"),
            confidence=min(confidence(decision.get("confidence"), default=0.75), 0.45) if not citation_check["valid"] else confidence(decision.get("confidence"), default=0.75),
            provider=get_effective_provider_name(self.llm_provider),
            model=get_effective_model_name(self.llm_provider),
            thoughts=thoughts,
            started=started,
            metadata={"citationValidation": citation_check, "verifiedEvidenceRefs": verified_refs},
        )

    def from_context(self, *, thoughts: list[dict[str, Any]], started: float) -> AgentResult:
        chunks = self.context_manager.get_chunks_sorted_by_score()
        if not chunks:
            return self._result(
                answer="Không đủ bằng chứng trong dữ liệu cuộc họp để trả lời câu hỏi này.",
                evidence_state="not_enough_evidence",
                confidence=0.0,
                provider="agentic-rag-evidence-guard",
                model=None,
                thoughts=thoughts,
                started=started,
                metadata={"chunks": [], "tokenUsage": self.context_coordinator.token_summary()},
            )

        structured = _structured_projection(self.context_manager.context.query, chunks)
        if structured is not None:
            answer, evidence_refs, projection_confidence = structured
            citation_ids = list(dict.fromkeys(
                citation_id
                for chunk in chunks
                if set(chunk.evidence_refs).intersection(evidence_refs)
                for citation_id in chunk.citation_ids
            ))
            return self._result(
                answer=answer,
                evidence_state="grounded" if evidence_refs else "not_enough_evidence",
                confidence=projection_confidence if evidence_refs else 0.0,
                provider="agentic-rag-structured-projection",
                model=None,
                thoughts=thoughts,
                started=started,
                metadata={
                    "verifiedEvidenceRefs": evidence_refs,
                    "verifiedCitationIds": citation_ids,
                    "answerShape": build_query_plan(self.context_manager.context.query).answer_shape,
                },
            )

        verified_evidence_refs: list[str] = []
        try:
            response = self.llm_provider.generate_json(
                system_prompt=synthesis_system_prompt(),
                user_prompt=synthesis_user_prompt(
                    question=self.context_manager.context.query,
                    context=self.context_manager.format_context_for_llm(include_tool_history=False),
                ),
            )
            answer = response.get("answer")
            if not isinstance(answer, str) or not answer.strip():
                raise LLMProviderError("Synthesis response did not include an answer.")
            response_state = evidence_state(response.get("evidenceState"), has_context=True)
            response_confidence = confidence(response.get("confidence"), default=0.7)
            requested_citations = response.get("citations") if isinstance(response.get("citations"), list) else []
            requested_evidence_refs = response.get("evidenceRefs") if isinstance(response.get("evidenceRefs"), list) else []
            known_evidence_refs = {ref for chunk in chunks for ref in chunk.evidence_refs}
            verified_evidence_refs = list(dict.fromkeys(
                ref for ref in requested_evidence_refs
                if isinstance(ref, str) and ref in known_evidence_refs
            ))
            if requested_evidence_refs and not verified_evidence_refs:
                requested_citations = []
            elif verified_evidence_refs:
                requested_citations = list(dict.fromkeys(
                    citation_id
                    for chunk in chunks
                    if set(chunk.evidence_refs).intersection(verified_evidence_refs)
                    for citation_id in chunk.citation_ids
                ))
            citation_check = verify_answer_coverage(
                answer,
                chunks,
                requested_citations,
            )
            known_citation_ids = {
                citation_id
                for chunk in chunks
                for citation_id in chunk.citation_ids
            }
            verified_citation_ids = list(dict.fromkeys(
                citation_id
                for citation_id in requested_citations
                if isinstance(citation_id, str) and citation_id in known_citation_ids
            ))
            if not citation_check["valid"]:
                response_state = "partial"
                response_confidence = min(response_confidence, 0.45)
            structured_fallback = _entity_answer_fallback(self.context_manager.context.query, chunks)
            if structured_fallback and response_state == "not_enough_evidence":
                answer = structured_fallback
                response_state = "partial"
                response_confidence = min(response_confidence, 0.55)
            provider = get_effective_provider_name(self.llm_provider)
            model = get_effective_model_name(self.llm_provider)
        except Exception:
            answer = fallback_answer_from_context(chunks)
            response_state = "partial"
            response_confidence = 0.45
            provider = "agentic-rag-local-summary"
            model = None
            citation_check = verify_answer_coverage(answer, chunks)
            verified_citation_ids = list(dict.fromkeys(
                citation_id
                for chunk in chunks
                for citation_id in chunk.citation_ids
            ))
        return self._result(
            answer=answer,
            evidence_state=response_state,
            confidence=response_confidence,
            provider=provider,
            model=model,
            thoughts=thoughts,
            started=started,
            metadata={
                "citationValidation": citation_check,
                "verifiedCitationIds": verified_citation_ids,
                "verifiedEvidenceRefs": verified_evidence_refs,
            },
        )

    def fallback_from_retrieval(
        self,
        *,
        meeting_id: str,
        question: str,
        thoughts: list[dict[str, Any]],
        started: float,
        error: Exception,
    ) -> AgentResult:
        try:
            retrieved = self.retrieval_search.search_meeting(
                meeting_id=meeting_id, query=question
            )
        except Exception:
            retrieved = []
        chunks = [
            normalize_chunk({
                "chunkId": item.record.chunk_id,
                "text": item.record.text,
                "sourceType": item.record.source_type,
                "sectionType": item.record.section_type,
                "jsonPointer": item.record.json_pointer,
                "citationIds": list(item.record.citation_ids or []),
                "segmentIds": list(item.record.segment_ids or []),
                "startMs": item.record.start_ms,
                "endMs": item.record.end_ms,
                "metadata": item.record.metadata_json or {},
                "score": item.score,
            })
            for item in retrieved[:6]
        ]
        self.context_manager.add_chunks([to_context_chunk(chunk) for chunk in chunks])
        return self._result(
            answer=fallback_answer_from_context(self.context_manager.get_chunks_sorted_by_score()),
            evidence_state="partial" if chunks else "not_enough_evidence",
            confidence=0.4 if chunks else 0.0,
            provider="agentic-rag-fallback",
            model=None,
            thoughts=thoughts,
            started=started,
            metadata={"error": {"type": type(error).__name__, "message": str(error)}},
        )

    def _result(
        self,
        *,
        answer: str,
        evidence_state: str,
        confidence: float,
        provider: str,
        model: str | None,
        thoughts: list[dict[str, Any]],
        started: float,
        metadata: dict[str, Any] | None = None,
    ) -> AgentResult:
        return AgentResult(
            answer=answer,
            evidence_state=evidence_state,
            confidence=confidence,
            provider=provider,
            model=model,
            iterations=len(thoughts),
            total_duration_ms=elapsed_ms(started),
            tool_calls_summary=self.context_coordinator.tool_call_summary(),
            agent_thoughts=thoughts,
            metadata={
                "chunks": self.context_coordinator.chunks_for_metadata(),
                "tokenUsage": self.context_coordinator.token_summary(),
                **(metadata or {}),
            },
        )


def _entity_answer_fallback(question: str, chunks: list[Any]) -> str | None:
    """Answer entity-name questions from canonical entity chunks when the LLM is overly conservative."""
    normalized = unicodedata.normalize("NFKD", question.lower())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    if not any(term in normalized for term in ("cua hang", "store", "shop", "merchant", "thuong hieu", "brand")):
        return None
    entities: list[tuple[str, str]] = []
    for chunk in chunks:
        if chunk.section_type != "entity.profile":
            continue
        match = re.search(r"type:\s*([^.]*)\.\s*confidence:.*?name:\s*([^.]*)\.", chunk.text, re.IGNORECASE)
        if match:
            entities.append((match.group(1).strip(), match.group(2).strip()))
    if not entities:
        return None
    preferred = [name for entity_type, name in entities if entity_type.lower() in {"company", "store", "shop", "brand"}]
    names = list(dict.fromkeys(preferred or [name for _, name in entities]))
    return (
        "Dữ liệu không gắn nhãn trực tiếp là cửa hàng, nhưng ghi nhận đơn vị/công ty được nhắc đến là: "
        + ", ".join(names)
        + "."
    )


def _structured_projection(question: str, chunks: list[Any]) -> tuple[str, list[str], float] | None:
    """Return a deterministic answer for common generic record projections."""
    plan = build_query_plan(question)
    records = [
        (chunk, chunk.metadata.get("recordFields") or {})
        for chunk in chunks
        if chunk.metadata.get("recordId") and isinstance(chunk.metadata.get("recordFields") or {}, dict)
    ]
    if plan.answer_shape == "count":
        for chunk, fields in records:
            if chunk.metadata.get("subtype") in {"participant_count", "speaker_count"} and isinstance(fields.get("value"), int | float):
                return f"Có {int(fields['value'])} người nói/participant được ghi nhận trong cuộc họp.", chunk.evidence_refs, 0.95
        return "Không tìm thấy record đếm participant đủ tin cậy trong dữ liệu cuộc họp.", [], 0.0
    if plan.answer_shape == "participant_list":
        profiles = []
        mentioned = []
        refs: list[str] = []
        for chunk, fields in records:
            if chunk.record_type != "participant":
                continue
            name = fields.get("displayName") or fields.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            refs.extend(chunk.evidence_refs)
            if chunk.record_subtype == "speaker_profile":
                profiles.append(name.strip())
            elif fields.get("isMentionedOnly"):
                mentioned.append(name.strip())
            else:
                profiles.append(name.strip())
        profiles = list(dict.fromkeys(profiles))
        mentioned = [name for name in dict.fromkeys(mentioned) if name not in profiles]
        if not profiles and not mentioned:
            return "Không tìm thấy thông tin participant đủ tin cậy.", [], 0.0
        answer = "Speaker/participant được ghi nhận: " + ", ".join(profiles) + "." if profiles else ""
        if mentioned:
            answer += " Người được nhắc đến nhưng chưa xác định chắc chắn là speaker: " + ", ".join(mentioned) + "."
        return answer.strip(), list(dict.fromkeys(refs)), 0.9
    if plan.answer_shape in {"actor_target", "location"}:
        matches = []
        refs: list[str] = []
        for chunk, fields in records:
            actor = fields.get("actor") or fields.get("owner") or fields.get("ownerName")
            target = fields.get("target") or fields.get("venue") or fields.get("location")
            if actor or target:
                matches.append((actor, target))
                refs.extend(chunk.evidence_refs)
        if not matches:
            return "Không có relationship actor/target đủ rõ trong dữ liệu cuộc họp.", [], 0.0
        if plan.answer_shape == "location":
            targets = list(dict.fromkeys(str(target) for _, target in matches if target))
            if targets:
                return "Địa điểm/entity được ghi nhận: " + ", ".join(targets) + ".", list(dict.fromkeys(refs)), 0.8
            return "Chưa có địa điểm cụ thể được ghi nhận.", [], 0.0
        targeted = [(actor, target) for actor, target in matches if target]
        pairs = [f"{actor or 'Chưa xác định'} thực hiện hành động liên quan đến {target}" for actor, target in (targeted or matches)]
        return "; ".join(dict.fromkeys(pairs)) + ".", list(dict.fromkeys(refs)), 0.9
    if plan.answer_shape == "timeline":
        timed = []
        refs: list[str] = []
        for chunk, fields in records:
            temporal_text = str(fields.get("text") or chunk.text).lower()
            if any(key in fields for key in ("startMs", "endMs", "dueDate", "date", "time")) or any(term in temporal_text for term in ("appointment", "scheduled", "saturday", "friday", "december", "p.m.", "deadline", "thứ", "ngày", "giờ")):
                timed.append(chunk.text.replace("Event. ", "").replace("Action item. ", ""))
                refs.extend(chunk.evidence_refs)
        if timed:
            return "Các mốc thời gian được ghi nhận: " + " ".join(dict.fromkeys(timed)), list(dict.fromkeys(refs)), 0.85
    return None
