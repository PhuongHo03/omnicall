from typing import Any
import time

from sqlalchemy.orm import Session

from backend.configs.settings import Settings, get_settings
from backend.dependencies.auth import CurrentUserContext
from backend.dtos.meeting_dto import (
    MeetingChatAcceptedResponse,
    MeetingChatCitationResponse,
    MeetingChatHistoryResponse,
    MeetingChatMessageResponse,
    MeetingChatRequest,
)
from backend.models.enums import MeetingStatus
from backend.models.meeting_models import ChatMessage
from backend.providers.guardrail_provider import GuardrailProvider, GuardrailResult, get_guardrail_provider, safe_guardrail_check
from backend.providers.app_metrics_provider import AGENT_FAST_PATH_TOTAL, AGENT_ITERATIONS, AGENT_REPLANS, AGENT_TOOL_CALLS_TOTAL
from backend.providers.llm import (
    LLMProvider,
    get_llm_provider,
)
from backend.repositories.chat_repository import ChatMessageRepository
from backend.repositories.meeting_repository import MeetingAssetRepository, MeetingRepository
from backend.services.agent import AgenticRAGService
from backend.services.operational_log_service import OperationalLogService
from backend.services.retrieval.search_service import RetrievalSearchService
from backend.utils.exceptions import ApplicationError


class MeetingChatService:
    def __init__(
        self,
        session: Session,
        llm_provider: LLMProvider | None = None,
        retrieval_search: RetrievalSearchService | None = None,
        guardrail_provider: GuardrailProvider | None = None,
        settings: Settings | None = None,
        operational_logs: OperationalLogService | None = None,
        agentic_rag_service: AgenticRAGService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.meetings = MeetingRepository(session)
        self.assets = MeetingAssetRepository(session)
        self.chat_messages = ChatMessageRepository(session)
        self.retrieval_search = retrieval_search or RetrievalSearchService(session)
        self.llm_provider = llm_provider or get_llm_provider()
        self.guardrail_provider = guardrail_provider or get_guardrail_provider()
        self.operational_logs = operational_logs
        self.agentic_rag_service = agentic_rag_service or AgenticRAGService(
            session=session,
            llm_provider=self.llm_provider,
            retrieval_search=self.retrieval_search,
            operational_logs=operational_logs,
            settings=self.settings,
        )

    def ask(self, context: CurrentUserContext, meeting_id: str, request: MeetingChatRequest) -> MeetingChatAcceptedResponse:
        meeting = self.meetings.get_for_owner(meeting_id, context.user_id)
        if meeting is None:
            raise ApplicationError(404, "meeting_not_found", "Meeting was not found.")
        if meeting.status != MeetingStatus.READY:
            raise ApplicationError(409, "meeting_intelligence_not_ready", "Meeting intelligence is not ready for chat.")

        question = request.question.strip()
        if not question:
            raise ApplicationError(400, "empty_question", "Question must not be empty.")

        asset = self.assets.get_latest_for_meeting(meeting.id)
        log_context = {
            "workspace_id": context.user_id,
            "meeting_id": meeting.id,
            "meeting_name": meeting.title,
            "file": _asset_log_context(asset),
            "chat": _chat_log_context(question),
        }
        self._emit(
            level="info",
            flow="rag",
            stage="question",
            status="received",
            message="RAG question received.",
            **log_context,
            details={"questionLength": len(question)},
        )

        user_message = self.chat_messages.create(
            meeting_id=meeting.id,
            role="user",
            content=question,
            metadata={"guardrails": {}},
        )
        meeting.pending_chat_status = "queued"
        self.session.commit()

        from backend.tasks.chat_tasks import generate_chat_answer
        generate_chat_answer.delay(
            meeting_id=meeting.id,
            user_id=context.user_id,
            question=question,
            user_message_id=user_message.id,
            guardrails={},
        )

        self._emit(
            level="info",
            flow="rag",
            stage="question",
            status="queued",
            message="RAG answer generation queued.",
            **log_context,
        )
        return MeetingChatAcceptedResponse()

    def generate_answer(
        self,
        *,
        meeting_id: str,
        user_id: str,
        question: str,
        user_message_id: str,
        input_guardrails: dict,
        event_callback: Any = None,
    ) -> dict[str, str]:
        meeting = self.meetings.get_for_owner(meeting_id, user_id)
        if meeting is None:
            return {"status": "error", "error": "meeting_not_found"}

        user_message = self.chat_messages.get_by_id(user_message_id)
        if user_message is None:
            return {"status": "error", "error": "user_message_not_found"}

        meeting.pending_chat_status = "started"
        self.session.commit()

        asset = self.assets.get_latest_for_meeting(meeting.id)
        log_context = {
            "workspace_id": user_id,
            "meeting_id": meeting.id,
            "meeting_name": meeting.title,
            "file": _asset_log_context(asset),
            "chat": _chat_log_context(question),
        }

        if event_callback:
            event_callback({"type": "status", "stage": "input_guardrail", "message": "Đang kiểm tra câu hỏi..."})
        guardrail_started = time.perf_counter()
        input_guardrail = self._check_guardrail(
            enabled=self.settings.guardrail_input_enabled,
            kind="chat_input",
            text=question,
            metadata={"meetingId": meeting.id},
        )
        self._emit_guardrail(
            stage="input_guardrail",
            result=input_guardrail,
            duration_ms=_elapsed_ms(guardrail_started),
            message="Input guardrail check completed.",
            log_context=log_context,
        )

        effective_question = question
        self.chat_messages.update(
            user_message,
            content=effective_question,
            metadata={"guardrails": _guardrail_map(input=input_guardrail)},
        )
        self.session.commit()

        if input_guardrail and input_guardrail.action == "blocked":
            if event_callback:
                event_callback({"type": "blocked", "message": "Câu hỏi đã bị đánh dấu không an toàn"})
            self._emit(
                level="info",
                flow="rag",
                stage="answer",
                status="blocked",
                message="RAG question was blocked before retrieval.",
                **log_context,
                provider=input_guardrail.provider,
                model=input_guardrail.model,
                details=input_guardrail.to_metadata(),
            )
            meeting.pending_chat_status = None
            self._save_blocked_chat_response(
                meeting_id=meeting.id,
                user_message_id=user_message.id,
                user_content=user_message.content,
                guardrails={"input": input_guardrail.to_metadata()},
                safe_message=input_guardrail.safe_message or "Câu hỏi đã bị đánh dấu không an toàn",
            )
            return {"status": "blocked"}
        if event_callback:
            event_callback({"type": "status", "stage": "agent", "message": "Đang phân tích và tìm bằng chứng..."})
        self._emit(
            level="info",
            flow="rag",
            stage="agent",
            status="started",
            message="Agentic RAG answer generation started.",
            **log_context,
        )
        agent_result = self.agentic_rag_service.generate_answer(
            meeting_id=meeting.id,
            question=effective_question,
            event_callback=event_callback,
        )
        AGENT_ITERATIONS.observe(agent_result.iterations)
        replans = agent_result.metadata.get("replans", 0)
        if isinstance(replans, int) and replans > 0:
            AGENT_REPLANS.inc(replans)
        if agent_result.evidence_state == "fast_path":
            AGENT_FAST_PATH_TOTAL.inc()
        for tool_call in agent_result.tool_calls_summary:
            tool_name = tool_call.get("tool") if isinstance(tool_call, dict) else None
            if isinstance(tool_name, str):
                AGENT_TOOL_CALLS_TOTAL.labels(tool_name).inc()
        answer_payload = agent_result.to_answer_payload()
        agent_chunks = agent_result.metadata.get("chunks", [])
        verified_citation_ids = agent_result.metadata.get("verifiedCitationIds")
        if verified_citation_ids is None:
            # Compatibility for custom/legacy AgentResult implementations that
            # predate the explicit synthesizer citation metadata.
            verified_citation_ids = list(dict.fromkeys(
                citation_id
                for chunk in agent_chunks
                if isinstance(chunk, dict)
                for citation_id in chunk.get("citationIds") or []
                if isinstance(citation_id, str)
            ))
        citations = _citation_responses_from_chunks(agent_chunks, verified_citation_ids)
        retrieved_chunk_ids = [
            chunk.get("chunkId")
            for chunk in agent_chunks
            if isinstance(chunk, dict) and isinstance(chunk.get("chunkId"), str)
        ]
        self._emit(
            level="info" if answer_payload.get("evidenceState") != "error" else "error",
            flow="rag",
            stage="agent",
            status="succeeded" if answer_payload.get("evidenceState") != "error" else "failed",
            message="Agentic RAG answer generated.",
            **log_context,
            provider=answer_payload.get("provider"),
            model=answer_payload.get("model"),
            duration_ms=agent_result.total_duration_ms,
            details={
                "evidenceState": answer_payload.get("evidenceState"),
                "confidence": answer_payload.get("confidence"),
                "citationCount": len(citations),
                "retrievedChunkCount": len(retrieved_chunk_ids),
                "iterations": agent_result.iterations,
            },
        )

        guardrail_started = time.perf_counter()
        if event_callback:
            event_callback({"type": "status", "stage": "output_guardrail", "message": "Đang kiểm tra câu trả lời..."})
        output_guardrail = self._check_guardrail(
            enabled=self.settings.guardrail_output_enabled,
            kind="answer",
            text=answer_payload["answer"],
            metadata={
                "meetingId": meeting.id,
                "hasCitations": bool(citations),
                "evidenceState": answer_payload["evidenceState"],
            },
        )
        self._emit_guardrail(
            stage="output_guardrail",
            result=output_guardrail,
            duration_ms=_elapsed_ms(guardrail_started),
            message="Answer guardrail check completed.",
            log_context=log_context,
        )
        answer_payload, citations = _apply_output_guardrail(answer_payload, citations, output_guardrail)
        guardrails = _guardrail_map(
            input=input_guardrail,
            output=output_guardrail,
        )

        self.chat_messages.create(
            meeting_id=meeting.id,
            role="assistant",
            content=answer_payload["answer"],
            retrieved_chunk_ids=retrieved_chunk_ids,
            citations=[citation.model_dump() for citation in citations],
            metadata={
                "evidenceState": answer_payload["evidenceState"],
                "confidence": answer_payload["confidence"],
                "provider": answer_payload["provider"],
                "model": answer_payload.get("model"),
                "userMessageId": user_message_id,
                "agentIterations": answer_payload.get("agentIterations"),
                "agentToolCalls": answer_payload.get("agentToolCalls", []),
                "agentThoughts": answer_payload.get("agentThoughts", []),
                "agentReplans": agent_result.metadata.get("replans", 0),
                "agentQueryPlan": agent_result.metadata.get("queryPlan", {}),
                "agent": {
                    "durationMs": agent_result.total_duration_ms,
                    "tokenUsage": agent_result.metadata.get("tokenUsage", {}),
                    "error": agent_result.metadata.get("error"),
                },
                "rerank": self.retrieval_search.last_rerank_metadata,
                "guardrails": guardrails,
                "guardrailDecisionCounts": _decision_counts(guardrails),
            },
        )
        meeting.pending_chat_status = None
        self.session.commit()
        if event_callback:
            if answer_payload.get("evidenceState") == "blocked":
                event_callback({"type": "blocked", "message": answer_payload["answer"]})
            else:
                event_callback({"type": "done", "answer": answer_payload["answer"]})
        self._emit(
            level="info",
            flow="rag",
            stage="answer",
            status="succeeded",
            message="RAG answer persisted.",
            **log_context,
            provider=answer_payload.get("provider"),
            model=answer_payload.get("model"),
            details={
                "evidenceState": answer_payload.get("evidenceState"),
                "confidence": answer_payload.get("confidence"),
                "citationCount": len(citations),
                "retrievedChunkCount": len(retrieved_chunk_ids),
            },
        )
        return {"status": "succeeded"}

    def save_error_response(
        self,
        *,
        meeting_id: str,
        user_message_id: str,
        guardrails: dict | None = None,
    ) -> None:
        if self.chat_messages.get_response_for_user_message(
            meeting_id=meeting_id,
            user_message_id=user_message_id,
        ) is not None:
            return
        self.chat_messages.create(
            meeting_id=meeting_id,
            role="assistant",
            content="Không thể tạo câu trả lời lúc này. Vui lòng thử lại sau.",
            metadata={
                "evidenceState": "error",
                "confidence": 0.0,
                "provider": "system",
                "userMessageId": user_message_id,
                "guardrails": guardrails or {},
            },
        )
        self.session.commit()

    def _check_guardrail(
        self,
        *,
        enabled: bool,
        kind: str,
        text: str,
        metadata: dict | None = None,
    ) -> GuardrailResult | None:
        if not enabled:
            return None
        return safe_guardrail_check(
            self.guardrail_provider,
            kind=kind,  # type: ignore[arg-type]
            text=text,
            strict_mode=self.settings.guardrail_strict_mode,
            metadata=metadata,
        )

    def _save_blocked_chat_response(
        self,
        *,
        meeting_id: str,
        user_message_id: str,
        user_content: str,
        guardrails: dict,
        safe_message: str,
    ) -> None:
        assistant = self.chat_messages.create(
            meeting_id=meeting_id,
            role="assistant",
            content=safe_message,
            metadata={
                "evidenceState": "blocked",
                "confidence": 1.0,
                "provider": "local-guardrail",
                "userMessageId": user_message_id,
                "guardrails": guardrails,
                "guardrailDecisionCounts": _decision_counts(guardrails),
            },
        )
        self.session.commit()
        meeting = self.meetings.get(meeting_id)
        asset = self.assets.get_latest_for_meeting(meeting_id)
        self._emit(
            level="info",
            flow="rag",
            stage="answer",
            status="succeeded",
            message="Blocked RAG response persisted and returned.",
            meeting_id=meeting_id,
            meeting_name=meeting.title if meeting else None,
            file=_asset_log_context(asset),
            chat={
                **_chat_log_context(user_content),
                "messageId": assistant.id,
            },
            provider="local-guardrail",
            details={"evidenceState": "blocked", "guardrails": guardrails},
        )

    def get_history(self, context: CurrentUserContext, meeting_id: str) -> MeetingChatHistoryResponse:
        meeting = self.meetings.get_for_owner(meeting_id, context.user_id)
        if meeting is None:
            raise ApplicationError(404, "meeting_not_found", "Meeting was not found.")
        messages = self.chat_messages.list_for_meeting(meeting_id=meeting.id)
        return MeetingChatHistoryResponse(
            meeting_id=meeting.id,
            title=meeting.title,
            messages=[_message_response(message) for message in messages],
        )

    def _emit_guardrail(
        self,
        *,
        stage: str,
        result: GuardrailResult | None,
        duration_ms: int,
        message: str,
        log_context: dict,
    ) -> None:
        metadata = result.to_metadata() if result else {"enabled": False}
        provider_error = result is not None and "provider_error" in result.categories
        self._emit(
            level="info" if not provider_error or result.action == "allowed" else "error",
            flow="rag",
            stage=stage,
            status="warned" if provider_error and result.action == "allowed" else "failed" if provider_error else "succeeded",
            message=(
                f"{message} Provider unavailable; continuing with warning."
                if provider_error and result.action == "allowed"
                else f"{message} Provider unavailable."
                if provider_error
                else message
            ),
            **log_context,
            provider=result.provider if result else "disabled",
            model=result.model if result else None,
            duration_ms=duration_ms,
            details=metadata,
            error_type="GuardrailProviderError" if provider_error and result.action != "allowed" else None,
            error_message=result.safe_message if provider_error and result.action != "allowed" else None,
        )

    def _emit(self, **event) -> None:
        if self.operational_logs is not None:
            self.operational_logs.emit(**event)


def _asset_log_context(asset) -> dict:
    if asset is None:
        return {}
    return {
        "id": asset.id,
        "name": asset.file_name,
        "contentType": asset.content_type,
        "sizeBytes": asset.size_bytes,
        "objectKey": asset.object_key,
    }


def _chat_log_context(question: str) -> dict:
    normalized = " ".join(question.split())
    return {
        "questionPreview": normalized[:240],
    }


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _apply_output_guardrail(
    answer_payload: dict,
    citations: list[MeetingChatCitationResponse],
    output_guardrail: GuardrailResult | None,
) -> tuple[dict, list[MeetingChatCitationResponse]]:
    if output_guardrail and output_guardrail.action == "blocked":
        return (
            {
                "answer": output_guardrail.safe_message or "Câu trả lời đã bị đánh dấu không an toàn",
                "evidenceState": "blocked",
                "confidence": min(float(answer_payload.get("confidence", 0.0)), output_guardrail.confidence),
                "provider": output_guardrail.provider,
            },
            [],
        )
    if answer_payload.get("evidenceState") in {"grounded", "partial"} and not citations:
        return (
            {
                **answer_payload,
                "answer": "Không đủ bằng chứng trong dữ liệu cuộc họp để trả lời câu hỏi này.",
                "evidenceState": "not_enough_evidence",
                "confidence": 0.0,
                "provider": "local-output-evidence-guard",
            },
            [],
        )
    return answer_payload, citations


def _guardrail_map(**results: GuardrailResult | None) -> dict:
    return {
        key: result.to_metadata()
        for key, result in results.items()
        if result is not None
    }


def _decision_counts(guardrails: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in guardrails.values():
        action = result.get("action") if isinstance(result, dict) else None
        if isinstance(action, str):
            counts[action] = counts.get(action, 0) + 1
    return counts


def _citation_responses_from_chunks(
    chunks: list[dict],
    verified_citation_ids: list[str] | None,
) -> list[MeetingChatCitationResponse]:
    allowed = set(verified_citation_ids or [])
    if not allowed:
        return []
    responses: list[MeetingChatCitationResponse] = []
    seen: set[str] = set()
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        for citation_id in chunk.get("citationIds") or []:
            if not isinstance(citation_id, str) or citation_id not in allowed or citation_id in seen:
                continue
            seen.add(citation_id)
            responses.append(_citation_response_from_chunk(chunk, citation_id))
    return responses


def _citation_response_from_chunk(chunk: dict, citation_id: str) -> MeetingChatCitationResponse:
    metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
    citation_quotes = metadata.get("citationQuotes") if isinstance(metadata.get("citationQuotes"), dict) else {}
    citation_locations = metadata.get("citationLocations") if isinstance(metadata.get("citationLocations"), dict) else {}
    location = citation_locations.get(citation_id) if isinstance(citation_locations.get(citation_id), dict) else {}
    quote = citation_quotes.get(citation_id) if isinstance(citation_quotes.get(citation_id), str) else chunk.get("text")
    location_segment_ids = location.get("segmentIds")
    segment_ids = (
        list(location_segment_ids)
        if isinstance(location_segment_ids, list)
        else list(chunk.get("segmentIds") or [])
    )
    start_ms = location.get("startMs") if isinstance(location.get("startMs"), int) and location.get("startMs") >= 0 else chunk.get("startMs")
    end_ms = location.get("endMs") if isinstance(location.get("endMs"), int) and location.get("endMs") >= 0 else chunk.get("endMs")
    return MeetingChatCitationResponse(
        citation_id=citation_id,
        chunk_id=str(chunk.get("chunkId") or ""),
        source_type=str(chunk.get("sourceType") or ""),
        section_type=str(chunk.get("sectionType") or ""),
        json_pointer=str(chunk.get("jsonPointer") or ""),
        segment_ids=segment_ids,
        start_ms=start_ms if isinstance(start_ms, int) and start_ms >= 0 else None,
        end_ms=end_ms if isinstance(end_ms, int) and end_ms >= 0 else None,
        quote=str(quote or ""),
    )


def _normalize_legacy_citation(citation: dict) -> list[dict]:
    """Normalize Phase 26 chunk citations for history reads."""
    citation_ids = citation.get("citation_ids") or []
    if not citation_ids:
        return []
    return [
        {
            "citation_id": citation_id,
            "chunk_id": citation.get("chunk_id", ""),
            "source_type": citation.get("source_type", ""),
            "section_type": citation.get("section_type", ""),
            "json_pointer": citation.get("json_pointer", ""),
            "segment_ids": list(citation.get("segment_ids") or []),
            "start_ms": citation.get("start_ms"),
            "end_ms": citation.get("end_ms"),
            "quote": citation.get("text", ""),
        }
        for citation_id in citation_ids
        if isinstance(citation_id, str)
    ]

def _message_response(message: ChatMessage) -> MeetingChatMessageResponse:
    normalized_citations: list[dict] = []
    for citation in message.citations or []:
        if not isinstance(citation, dict):
            continue
        if citation.get("citation_id"):
            normalized_citations.append(citation)
        else:
            normalized_citations.extend(_normalize_legacy_citation(citation))
    return MeetingChatMessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        retrieved_chunk_ids=list(message.retrieved_chunk_ids or []),
        citations=[MeetingChatCitationResponse(**citation) for citation in normalized_citations],
        metadata=message.metadata_json or {},
        created_at=message.created_at,
    )
