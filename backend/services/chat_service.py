from dataclasses import replace
import time

from sqlalchemy.orm import Session

from backend.configs.settings import Settings, get_settings
from backend.dependencies.auth import CurrentUserContext
from backend.dtos.meeting_dto import (
    MeetingChatCitationResponse,
    MeetingChatHistoryResponse,
    MeetingChatMessageResponse,
    MeetingChatRequest,
    MeetingChatResponse,
)
from backend.models.enums import MeetingStatus
from backend.models.meeting_models import ChatMessage, MeetingChunkRecord
from backend.providers.guardrail_provider import GuardrailProvider, GuardrailResult, get_guardrail_provider, safe_guardrail_check
from backend.providers.llm_provider import (
    LLMProvider,
    LLMProviderError,
    get_effective_model_name,
    get_effective_provider_name,
    get_llm_provider,
)
from backend.repositories.chat_repository import ChatMessageRepository
from backend.repositories.meeting_repository import MeetingAssetRepository, MeetingRepository
from backend.services.operational_log_service import OperationalLogService
from backend.services.retrieval_search_service import RetrievedChunk, RetrievalSearchService
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

    def ask(self, context: CurrentUserContext, meeting_id: str, request: MeetingChatRequest) -> MeetingChatResponse:
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
            "language": request.language or meeting.language,
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

        guardrail_started = time.perf_counter()
        input_guardrail = self._check_guardrail(
            enabled=self.settings.guardrail_input_enabled,
            kind="chat_input",
            text=question,
            metadata={"meetingId": meeting.id, "language": request.language or meeting.language},
        )
        self._emit_guardrail(
            stage="input_guardrail",
            result=input_guardrail,
            duration_ms=_elapsed_ms(guardrail_started),
            message="Input guardrail check completed.",
            log_context=log_context,
        )
        if input_guardrail and input_guardrail.action == "block":
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
            return self._save_blocked_chat_response(
                context=context,
                meeting_id=meeting.id,
                user_content="[blocked by guardrail]",
                guardrails={"input": input_guardrail.to_metadata()},
                safe_message=input_guardrail.safe_message or _blocked_message(),
            )

        effective_question = input_guardrail.redacted_text if input_guardrail and input_guardrail.redacted_text else question
        self.chat_messages.create(
            meeting_id=meeting.id,
            role="user",
            content=effective_question,
            metadata={
                "language": request.language or meeting.language,
                "guardrails": _guardrail_map(input=input_guardrail),
            },
        )

        self._emit(
            level="info",
            flow="rag",
            stage="retrieval",
            status="started",
            message="RAG retrieval started.",
            **log_context,
        )
        try:
            retrieved = self.retrieval_search.search_meeting(
                workspace_id=context.user_id,
                meeting_id=meeting.id,
                query=effective_question,
            )
        except Exception as exc:
            self._emit(
                level="error",
                flow="rag",
                stage="retrieval",
                status="failed",
                message="RAG retrieval failed.",
                **log_context,
                provider=self.retrieval_search.embedding_provider.provider_name,
                model=self.retrieval_search.embedding_provider.model_name,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise
        search_metadata = self.retrieval_search.last_search_metadata
        embedding_metadata = search_metadata.get("embedding", {})
        self._emit(
            level="info",
            flow="rag",
            stage="query_embedding",
            status="succeeded",
            message="Question embedding generated.",
            **log_context,
            provider=embedding_metadata.get("provider"),
            model=embedding_metadata.get("model"),
            duration_ms=embedding_metadata.get("durationMs"),
            details={"dimensions": embedding_metadata.get("dimensions")},
        )
        retrieval_metadata = search_metadata.get("retrieval", {})
        self._emit(
            level="info",
            flow="rag",
            stage="retrieval",
            status="succeeded",
            message="Meeting evidence retrieval completed.",
            **log_context,
            provider=retrieval_metadata.get("provider"),
            model=self.settings.milvus_collection if retrieval_metadata.get("provider") != "postgres-fallback" else None,
            duration_ms=retrieval_metadata.get("durationMs"),
            details={
                **retrieval_metadata,
                "resultCount": search_metadata.get("resultCount"),
                "chunkIds": [item.record.chunk_id for item in retrieved],
            },
        )
        rerank_metadata = search_metadata.get("rerank", {})
        rerank_failed = rerank_metadata.get("status") == "unavailable"
        self._emit(
            level="error" if rerank_failed else "info",
            flow="rag",
            stage="rerank",
            status="failed" if rerank_failed else "succeeded",
            message="Reranker failed; retrieval order fallback was used." if rerank_failed else "Retrieved evidence reranked.",
            **log_context,
            provider=rerank_metadata.get("provider"),
            model=rerank_metadata.get("model"),
            duration_ms=rerank_metadata.get("durationMs"),
            details=rerank_metadata,
            error_type="RerankProviderError" if rerank_failed else None,
            error_message=rerank_metadata.get("error") if rerank_failed else None,
        )
        citations = [_citation_response(item.record) for item in retrieved[:4]]
        if not retrieved:
            answer_payload = {
                "answer": "Không đủ bằng chứng trong dữ liệu cuộc họp để trả lời câu hỏi này.",
                "evidenceState": "not_enough_evidence",
                "confidence": 0.0,
                "provider": "local-evidence-guard",
            }
        else:
            guardrail_started = time.perf_counter()
            context_guardrail = self._check_guardrail(
                enabled=self.settings.guardrail_context_enabled,
                kind="retrieved_context",
                text=_retrieved_context_text(retrieved),
                metadata={"meetingId": meeting.id, "source": "retrieved_context"},
            )
            context_guardrail = _downgrade_non_strict_context_block(
                context_guardrail,
                strict_mode=self.settings.guardrail_strict_mode,
            )
            self._emit_guardrail(
                stage="context_guardrail",
                result=context_guardrail,
                duration_ms=_elapsed_ms(guardrail_started),
                message="Retrieved context guardrail check completed.",
                log_context=log_context,
            )
            if context_guardrail and context_guardrail.action == "block":
                citations = []
                answer_payload = {
                    "answer": context_guardrail.safe_message or _blocked_message(),
                    "evidenceState": "blocked",
                    "confidence": context_guardrail.confidence,
                    "provider": context_guardrail.provider,
                }
            else:
                answer_payload = self._generate_answer(question=effective_question, retrieved=retrieved)
                answer_error = answer_payload.pop("_error", None)
                fallback_error = answer_payload.pop("_fallbackError", None)
                answer_duration_ms = answer_payload.pop("_durationMs", None)
                if answer_error:
                    self._emit(
                        level="error",
                        flow="rag",
                        stage="answer_llm",
                        status="failed",
                        message="LLM answer generation failed; local evidence fallback was used.",
                        **log_context,
                        provider=answer_error.get("provider"),
                        model=answer_error.get("model"),
                        duration_ms=answer_duration_ms,
                        error_type=answer_error.get("type"),
                        error_message=answer_error.get("message"),
                    )
                elif fallback_error:
                    self._emit(
                        level="error",
                        flow="rag",
                        stage="answer_llm_primary",
                        status="failed",
                        message="Primary LLM provider failed; Ollama fallback was activated.",
                        **log_context,
                        provider=fallback_error.get("provider"),
                        model=fallback_error.get("model"),
                        duration_ms=answer_duration_ms,
                        error_type=fallback_error.get("type"),
                        error_message=fallback_error.get("message"),
                    )
                self._emit(
                    level="info",
                    flow="rag",
                    stage="answer_llm" if not answer_error else "answer_fallback",
                    status="succeeded",
                    message="Grounded LLM answer generated." if not answer_error else "Local evidence fallback answer generated.",
                    **log_context,
                    provider=answer_payload.get("provider"),
                    model=answer_payload.get("model"),
                    duration_ms=answer_duration_ms,
                    details={
                        "evidenceState": answer_payload.get("evidenceState"),
                        "confidence": answer_payload.get("confidence"),
                        "citationCount": len(citations),
                    },
                )

        guardrail_started = time.perf_counter()
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
            context=locals().get("context_guardrail"),
            output=output_guardrail,
        )

        assistant = self.chat_messages.create(
            meeting_id=meeting.id,
            role="assistant",
            content=answer_payload["answer"],
            retrieved_chunk_ids=[item.record.chunk_id for item in retrieved],
            citations=[citation.model_dump() for citation in citations],
            metadata={
                "evidenceState": answer_payload["evidenceState"],
                "confidence": answer_payload["confidence"],
                "provider": answer_payload["provider"],
                "model": answer_payload.get("model"),
                "rerank": self.retrieval_search.last_rerank_metadata,
                "guardrails": guardrails,
                "guardrailDecisionCounts": _decision_counts(guardrails),
            },
        )
        self.session.commit()
        self.session.refresh(assistant)
        self._emit(
            level="info",
            flow="rag",
            stage="answer",
            status="succeeded",
            message="RAG answer persisted and returned.",
            **{
                **log_context,
                "chat": {
                    **log_context["chat"],
                    "messageId": assistant.id,
                },
            },
            provider=answer_payload.get("provider"),
            model=answer_payload.get("model"),
            details={
                "evidenceState": answer_payload.get("evidenceState"),
                "confidence": answer_payload.get("confidence"),
                "citationCount": len(citations),
                "retrievedChunkCount": len(retrieved),
            },
        )
        return MeetingChatResponse(
            answer=assistant.content,
            evidence_state=answer_payload["evidenceState"],
            citations=citations,
            message=_message_response(assistant),
        )

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
        context: CurrentUserContext,
        meeting_id: str,
        user_content: str,
        guardrails: dict,
        safe_message: str,
    ) -> MeetingChatResponse:
        self.chat_messages.create(
            meeting_id=meeting_id,
            role="user",
            content=user_content,
            metadata={"guardrails": guardrails},
        )
        assistant = self.chat_messages.create(
            meeting_id=meeting_id,
            role="assistant",
            content=safe_message,
            metadata={
                "evidenceState": "blocked",
                "confidence": 1.0,
                "provider": "local-guardrail",
                "guardrails": guardrails,
                "guardrailDecisionCounts": _decision_counts(guardrails),
            },
        )
        self.session.commit()
        self.session.refresh(assistant)
        meeting = self.meetings.get_for_owner(meeting_id, context.user_id)
        asset = self.assets.get_latest_for_meeting(meeting_id)
        self._emit(
            level="info",
            flow="rag",
            stage="answer",
            status="succeeded",
            message="Blocked RAG response persisted and returned.",
            workspace_id=context.user_id,
            meeting_id=meeting_id,
            meeting_name=meeting.title if meeting else None,
            language=meeting.language if meeting else None,
            file=_asset_log_context(asset),
            chat={
                **_chat_log_context(user_content),
                "messageId": assistant.id,
            },
            provider="local-guardrail",
            details={"evidenceState": "blocked", "guardrails": guardrails},
        )
        return MeetingChatResponse(
            answer=assistant.content,
            evidence_state="blocked",
            citations=[],
            message=_message_response(assistant),
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

    def _generate_answer(self, *, question: str, retrieved: list[RetrievedChunk]) -> dict:
        started = time.perf_counter()
        try:
            response = self.llm_provider.generate_json(
                system_prompt=_chat_system_prompt(),
                user_prompt=_chat_user_prompt(question=question, retrieved=retrieved),
            )
            answer = response.get("answer")
            if not isinstance(answer, str) or not answer.strip():
                raise LLMProviderError("Chat provider response did not include an answer.")
            evidence_state = response.get("evidenceState")
            if evidence_state not in {"grounded", "partial", "not_enough_evidence"}:
                evidence_state = "grounded"
            confidence = response.get("confidence", 0.7)
            if not isinstance(confidence, int | float):
                confidence = 0.7
            payload = {
                "answer": answer.strip(),
                "evidenceState": evidence_state,
                "confidence": float(confidence),
                "provider": get_effective_provider_name(self.llm_provider),
                "model": get_effective_model_name(self.llm_provider),
                "_durationMs": _elapsed_ms(started),
            }
            if getattr(self.llm_provider, "last_fallback_used", False):
                primary = getattr(self.llm_provider, "primary", None)
                payload["_fallbackError"] = {
                    "type": getattr(self.llm_provider, "last_primary_error_type", "LLMProviderError"),
                    "message": getattr(self.llm_provider, "last_primary_error_message", "Primary LLM provider failed."),
                    "provider": getattr(primary, "provider_name", None),
                    "model": getattr(primary, "model_name", None),
                }
            return payload
        except LLMProviderError as exc:
            return {
                "answer": _fallback_answer(retrieved),
                "evidenceState": "partial",
                "confidence": 0.45,
                "provider": "local-retrieval-summary",
                "model": None,
                "_durationMs": _elapsed_ms(started),
                "_error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "provider": get_effective_provider_name(self.llm_provider),
                    "model": get_effective_model_name(self.llm_provider),
                },
            }

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
        fail_open_provider_error = provider_error and result.action == "warn"
        self._emit(
            level="info" if fail_open_provider_error or not provider_error else "error",
            flow="rag",
            stage=stage,
            status="warned" if fail_open_provider_error else "failed" if provider_error else "succeeded",
            message=(
                f"{message} Provider unavailable; continuing with warning."
                if fail_open_provider_error
                else f"{message} Provider unavailable."
                if provider_error
                else message
            ),
            **log_context,
            provider=result.provider if result else "disabled",
            model=result.model if result else None,
            duration_ms=duration_ms,
            details=metadata,
            error_type="GuardrailProviderError" if provider_error and not fail_open_provider_error else None,
            error_message=result.safe_message if provider_error and not fail_open_provider_error else None,
        )

    def _emit(self, **event) -> None:
        if self.operational_logs is not None:
            self.operational_logs.emit(**event)


def _chat_system_prompt() -> str:
    return (
        "You are a meeting intelligence analyst for Omnicall. "
        "Answer using only the provided meeting intelligence context; never add facts from outside the context. "
        "Prefer structured meeting intelligence over raw transcript fragments when both are available. "
        "Synthesize the most relevant evidence instead of copying one isolated chunk. "
        "If the question asks for a topic, issue, reason, decision, risk, timeline, or next action, include the concrete details that make the answer useful. "
        "For broad questions, answer with a concise overview plus key supporting points. "
        "For narrow factual questions, answer directly and mention any important caveat from the context. "
        "Use the user's language when possible. "
        "Return JSON with answer, evidenceState, and confidence. "
        "Use not_enough_evidence only when the provided context truly does not support the answer."
    )


def _chat_user_prompt(*, question: str, retrieved: list[RetrievedChunk]) -> str:
    context_lines = []
    for index, item in enumerate(retrieved[:6], start=1):
        chunk = item.record
        context_lines.append(
            "\n".join(
                [
                    f"[{index}] chunkId={chunk.chunk_id}",
                    f"sourceType={chunk.source_type}",
                    f"sectionType={chunk.section_type}",
                    f"jsonPointer={chunk.json_pointer}",
                    f"text={chunk.text}",
                ]
            )
        )
    return f"Question: {question}\n\nMeeting context:\n\n" + "\n\n".join(context_lines)


def _fallback_answer(retrieved: list[RetrievedChunk]) -> str:
    lines = [item.record.text.strip() for item in retrieved[:3] if item.record.text.strip()]
    if not lines:
        return "Không đủ bằng chứng trong dữ liệu cuộc họp để trả lời câu hỏi này."
    return "Dựa trên dữ liệu cuộc họp: " + " ".join(lines)


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


def _retrieved_context_text(retrieved: list[RetrievedChunk]) -> str:
    return "\n\n".join(item.record.text for item in retrieved[:6] if item.record.text.strip())


def _downgrade_non_strict_context_block(
    context_guardrail: GuardrailResult | None,
    *,
    strict_mode: bool,
) -> GuardrailResult | None:
    if context_guardrail is None or context_guardrail.action != "block" or strict_mode:
        return context_guardrail
    if _has_prompt_injection_category(context_guardrail.categories):
        return context_guardrail
    return replace(
        context_guardrail,
        action="warn",
        categories=list(dict.fromkeys([*context_guardrail.categories, "non_strict_context_block_downgraded"])),
    )


def _has_prompt_injection_category(categories: list[str]) -> bool:
    normalized = {category.lower() for category in categories}
    return bool(
        normalized.intersection(
            {
                "prompt_injection",
                "jailbreak",
                "system_prompt",
                "exfiltration",
                "bypass",
                "instruction_override",
            }
        )
    )


def _apply_output_guardrail(
    answer_payload: dict,
    citations: list[MeetingChatCitationResponse],
    output_guardrail: GuardrailResult | None,
) -> tuple[dict, list[MeetingChatCitationResponse]]:
    if output_guardrail and output_guardrail.action == "redact" and output_guardrail.redacted_text:
        answer_payload = {**answer_payload, "answer": output_guardrail.redacted_text}
    if output_guardrail and output_guardrail.action == "block":
        return (
            {
                "answer": output_guardrail.safe_message or "Không đủ bằng chứng trong dữ liệu cuộc họp để trả lời câu hỏi này.",
                "evidenceState": "not_enough_evidence",
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


def _blocked_message() -> str:
    return "Yêu cầu này đã bị chặn bởi guardrail vì không an toàn hoặc cố gắng vượt qua ngữ cảnh cuộc họp."


def _citation_response(chunk: MeetingChunkRecord) -> MeetingChatCitationResponse:
    return MeetingChatCitationResponse(
        chunk_id=chunk.chunk_id,
        source_type=chunk.source_type,
        section_type=chunk.section_type,
        json_pointer=chunk.json_pointer,
        citation_ids=list(chunk.citation_ids or []),
        segment_ids=list(chunk.segment_ids or []),
        start_ms=chunk.start_ms,
        end_ms=chunk.end_ms,
        text=chunk.text,
    )


def _message_response(message: ChatMessage) -> MeetingChatMessageResponse:
    return MeetingChatMessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        retrieved_chunk_ids=list(message.retrieved_chunk_ids or []),
        citations=[MeetingChatCitationResponse(**citation) for citation in message.citations],
        metadata=message.metadata_json or {},
        created_at=message.created_at,
    )
