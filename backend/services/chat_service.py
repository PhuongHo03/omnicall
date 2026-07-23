"""Durable lifecycle orchestration for Simple Evidence-First RAG."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.exc import IntegrityError
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
from backend.providers.guardrail_provider import GuardrailProvider, get_guardrail_provider, safe_guardrail_check
from backend.providers.llm import LLMProvider
from backend.repositories.chat_repository import ChatMessageRepository, ChatTurnRepository, FeedbackRevisionConflictError
from backend.repositories.meeting_repository import MeetingRepository
from backend.services.operational_log_service import OperationalLogService, get_operational_log_service
from backend.services.simple_rag import SimpleRAGPipeline
from backend.services.simple_rag.contracts import PipelineResult
from backend.services.simple_rag.output_policy_service import OutputPolicyService
from backend.utils.exceptions import ApplicationError
from backend.utils.secret_redaction import redact_secrets, redact_structure


_FEEDBACK_STATES = {"grounded", "partial", "direct"}
_BLOCKED_MESSAGE = "Yêu cầu này không thể được xử lý theo chính sách an toàn."
_ERROR_MESSAGE = "Không thể tạo câu trả lời đã được xác minh lúc này. Vui lòng thử lại sau."
_GUARDRAIL_FAILURE_CATEGORIES = {"provider_error", "parse_error", "timeout", "connection_error"}
_TRUSTED_HISTORY_MAX_TURNS = 6
_PROGRESS_MESSAGES = {
    "queued": "Đang chờ xử lý...",
    "request_gate": "Đang kiểm tra yêu cầu...",
    "query_interpretation": "Đang hiểu câu hỏi...",
    "retrieval": "Đang tìm bằng chứng...",
    "evidence_validation": "Đang xác thực bằng chứng...",
    "synthesis": "Đang tạo câu trả lời...",
    "answer_verification": "Đang kiểm tra câu trả lời...",
    "output_policy": "Đang áp dụng chính sách an toàn...",
    "persistence": "Đang lưu kết quả...",
}


class MeetingChatService:
    """Own turn lifecycle and persistence; delegate all RAG decisions."""

    def __init__(
        self,
        session: Session,
        llm_provider: LLMProvider | None = None,
        guardrail_provider: GuardrailProvider | None = None,
        settings: Settings | None = None,
        operational_logs: OperationalLogService | None = None,
        simple_pipeline: SimpleRAGPipeline | None = None,
        **_removed_legacy_dependencies: Any,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.meetings = MeetingRepository(session)
        self.chat_messages = ChatMessageRepository(session)
        self.chat_turns = ChatTurnRepository(session)
        self.guardrail_provider = guardrail_provider or get_guardrail_provider()
        self.output_policy = OutputPolicyService(self.guardrail_provider, self.settings)
        self.pipeline = simple_pipeline or SimpleRAGPipeline(session, llm_provider=llm_provider, settings=self.settings)
        self.operational_logs = operational_logs or get_operational_log_service()
        self.active_turn_id: str | None = None
        self.active_lease_token: str | None = None

    def ask(self, context: CurrentUserContext, meeting_id: str, request: MeetingChatRequest) -> MeetingChatAcceptedResponse:
        meeting = self.meetings.get_for_owner(meeting_id, context.user_id)
        if meeting is None:
            raise ApplicationError(404, "meeting_not_found", "Meeting was not found.")
        if meeting.status != MeetingStatus.READY:
            raise ApplicationError(409, "meeting_intelligence_not_ready", "Meeting intelligence is not ready for chat.")
        question, secret_found = redact_secrets(request.question.strip())
        if not question:
            raise ApplicationError(400, "empty_question", "Question must not be empty.")
        self.chat_turns.lock_meeting(meeting.id)
        if self.chat_turns.active_for_meeting(meeting.id) is not None:
            raise ApplicationError(409, "chat_busy", "This meeting is already processing a question.")
        try:
            user_message = self.chat_messages.create(
                meeting_id=meeting.id,
                role="user",
                content=question,
                metadata={"secretRedacted": secret_found, "requestedLanguage": request.language},
            )
            turn = self.chat_turns.create_queued(meeting_id=meeting.id, user_message_id=user_message.id)
            user_message.metadata_json = {
                "turnId": turn.id,
                "secretRedacted": secret_found,
                "requestedLanguage": request.language,
                "chatProgress": _progress_event(turn.id, "queued"),
            }
            meeting.pending_chat_status = "queued"
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ApplicationError(409, "chat_busy", "This meeting is already processing a question.") from exc
        from backend.tasks.chat_tasks import generate_chat_answer

        try:
            generate_chat_answer.delay(turn_id=turn.id)
        except Exception:
            # Reconciliation republishes the durable queued turn.
            pass
        return MeetingChatAcceptedResponse(turn_id=turn.id)

    def generate_answer(
        self,
        *,
        turn_id: str | None = None,
        meeting_id: str | None = None,
        user_id: str | None = None,
        question: str | None = None,
        user_message_id: str | None = None,
        event_callback: Any = None,
        **_unused: Any,
    ) -> dict[str, str]:
        turn = self._resolve_turn(turn_id, meeting_id, user_message_id, question)
        if turn is None:
            return {"status": "error", "error": "chat_turn_not_found"}
        if turn.status not in {"queued", "started"}:
            return {"status": "succeeded", "terminal": turn.status}
        if turn.status == "started":
            return {"status": "processing", "terminal": "started"}
        meeting = self.meetings.get(turn.meeting_id)
        user_message = self.chat_messages.get_by_id(turn.user_message_id)
        if meeting is None or user_message is None or (user_id and meeting.owner_user_id != user_id):
            self.chat_turns.mark_terminal(turn, status="error", assistant_message_id=None, error="invalid_persisted_turn")
            self.session.commit()
            return {"status": "error", "error": "invalid_chat_turn"}
        existing = self.chat_messages.get_response_for_user_message(meeting_id=meeting.id, user_message_id=user_message.id)
        if existing is not None:
            terminal = _turn_status((existing.metadata_json or {}).get("evidenceState"))
            self.chat_turns.mark_terminal(turn, status=terminal, assistant_message_id=existing.id)
            meeting.pending_chat_status = None
            self.session.commit()
            return {"status": "succeeded", "terminal": terminal}

        self.chat_turns.mark_started(turn, lease_seconds=self.settings.chat_turn_lease_seconds)
        turn_deadline = time.monotonic() + self.settings.rag_chat_turn_timeout_seconds
        self.active_turn_id = turn.id
        self.active_lease_token = turn.lease_token
        meeting.pending_chat_status = "started"
        self.session.commit()
        def report(stage: str) -> None:
            if event_callback:
                event_callback(_progress_event(turn.id, stage))

        report("request_gate")
        input_guardrail = safe_guardrail_check(
            self.guardrail_provider,
            kind="chat_input",
            text=user_message.content,
            metadata={"meetingId": meeting.id, "turnId": turn.id},
            strict_mode=True,
        )
        user_message.metadata_json = {
            **(user_message.metadata_json or {}),
            "guardrail": input_guardrail.to_metadata(),
        }
        self.session.commit()
        if _guardrail_failed(input_guardrail):
            return self._persist_result(turn, meeting, user_message, PipelineResult(
                _ERROR_MESSAGE,
                "error",
                "control",
                pipeline_trace={"version": 1, "contract": "simple-rag.v1", "stages": [
                    {"stage": "request_gate", "status": "failed", "durationMs": input_guardrail.latency_ms, "provider": input_guardrail.provider, "model": input_guardrail.model, "details": {"categories": input_guardrail.categories}}
                ]},
                terminal_status="error",
            ), event_callback)
        if input_guardrail.action == "blocked":
            return self._persist_result(turn, meeting, user_message, PipelineResult(
                _BLOCKED_MESSAGE,
                "blocked",
                "control",
                pipeline_trace={"version": 1, "contract": "simple-rag.v1", "stages": [
                    {"stage": "request_gate", "status": "blocked", "durationMs": input_guardrail.latency_ms, "provider": input_guardrail.provider, "model": input_guardrail.model, "details": {"categories": input_guardrail.categories}}
                ]},
                terminal_status="blocked",
            ), event_callback)

        history = self.chat_messages.list_completed_before(
            meeting_id=meeting.id,
            before_message_id=user_message.id,
            limit=_TRUSTED_HISTORY_MAX_TURNS,
        )
        result = self.pipeline.run(
            meeting_id=meeting.id,
            question=user_message.content,
            history=history,
            language_hint=(user_message.metadata_json or {}).get("requestedLanguage"),
            deadline_monotonic=turn_deadline,
            stage_callback=report,
        )
        if result.answer_origin_kind == "llm_synthesis":
            if time.monotonic() >= turn_deadline:
                result = PipelineResult(_ERROR_MESSAGE, "error", "control", pipeline_trace=result.pipeline_trace, terminal_status="error")
                return self._persist_result(turn, meeting, user_message, result, event_callback)
            report("output_policy")
            output_guardrail = self.output_policy.verify(result, meeting_id=meeting.id, turn_id=turn.id)
            if _guardrail_failed(output_guardrail):
                stages = [stage for stage in result.pipeline_trace.get("stages", []) if stage.get("stage") != "output_policy"]
                stages.append({"stage": "output_policy", "status": "failed", "durationMs": output_guardrail.latency_ms, "provider": output_guardrail.provider, "model": output_guardrail.model, "details": {"categories": output_guardrail.categories}})
                result = PipelineResult(_ERROR_MESSAGE, "error", "control", pipeline_trace={**result.pipeline_trace, "stages": stages}, terminal_status="error")
            elif output_guardrail.action == "blocked":
                stages = [stage for stage in result.pipeline_trace.get("stages", []) if stage.get("stage") != "output_policy"]
                stages.append({"stage": "output_policy", "status": "blocked", "durationMs": output_guardrail.latency_ms, "provider": output_guardrail.provider, "model": output_guardrail.model, "details": {"categories": output_guardrail.categories}})
                result = PipelineResult(_BLOCKED_MESSAGE, "blocked", "control", pipeline_trace={**result.pipeline_trace, "stages": stages}, terminal_status="blocked")
            else:
                stages = [stage for stage in result.pipeline_trace.get("stages", []) if stage.get("stage") != "output_policy"]
                stages.append({"stage": "output_policy", "status": "succeeded", "durationMs": output_guardrail.latency_ms, "provider": output_guardrail.provider, "model": output_guardrail.model, "details": {"categories": output_guardrail.categories}})
                result = PipelineResult(**{**result.__dict__, "pipeline_trace": {**result.pipeline_trace, "stages": stages}})
        return self._persist_result(turn, meeting, user_message, result, event_callback)

    def save_error_response(
        self,
        *,
        meeting_id: str,
        user_message_id: str,
        turn_id: str | None = None,
        expected_lease_token: str | None = None,
    ) -> None:
        turn = self.chat_turns.get(turn_id, for_update=True) if turn_id else self.chat_turns.get_by_user_message(user_message_id)
        meeting = self.meetings.get(meeting_id)
        user_message = self.chat_messages.get_by_id(user_message_id)
        if turn is None or meeting is None or user_message is None or turn.status not in {"queued", "started"}:
            return
        if turn.status == "queued":
            self.chat_turns.mark_started(turn, lease_seconds=self.settings.chat_turn_lease_seconds)
        token = expected_lease_token or turn.lease_token
        self.active_lease_token = token
        self._persist_result(turn, meeting, user_message, PipelineResult(_ERROR_MESSAGE, "error", "control", terminal_status="error"), None)

    def get_history(self, context: CurrentUserContext, meeting_id: str) -> MeetingChatHistoryResponse:
        meeting = self.meetings.get_for_owner(meeting_id, context.user_id)
        if meeting is None:
            raise ApplicationError(404, "meeting_not_found", "Meeting was not found.")
        messages = self.chat_messages.list_for_meeting(meeting_id=meeting.id)
        feedback = self.chat_messages.feedback_by_message_ids([message.id for message in messages])
        return MeetingChatHistoryResponse(
            meeting_id=meeting.id,
            title=meeting.title,
            messages=[_message_response(message, feedback.get(message.id)) for message in messages],
        )

    def record_progress(self, *, turn_id: str, event: dict[str, Any]) -> None:
        """Persist the latest turn-scoped progress event for SSE replay."""
        turn = self.chat_turns.get(turn_id)
        if turn is None or event.get("type") != "status":
            return
        user_message = self.chat_messages.get_by_id(turn.user_message_id)
        if user_message is None:
            return
        user_message.metadata_json = {
            **(user_message.metadata_json or {}),
            "chatProgress": event,
        }
        self.session.commit()

    def stream_snapshot(self, context: CurrentUserContext, meeting_id: str, turn_id: str | None) -> dict[str, Any] | None:
        """Return the durable latest event after ownership and turn checks."""
        meeting = self.meetings.get_for_owner(meeting_id, context.user_id)
        if meeting is None:
            raise ApplicationError(404, "meeting_not_found", "Meeting was not found.")
        turn = self.chat_turns.get(turn_id) if turn_id else self.chat_turns.active_for_meeting(meeting_id)
        if turn is None or turn.meeting_id != meeting_id:
            return None
        if turn.status in {"completed", "clarification_needed", "blocked", "error"} and turn.assistant_message_id:
            assistant = self.chat_messages.get_by_id(turn.assistant_message_id)
            if assistant is not None:
                event_type = "done" if turn.status == "completed" else turn.status
                message = _message_response(assistant).model_dump(mode="json")
                return {
                    "type": event_type,
                    "turnId": turn.id,
                    "answer": assistant.content,
                    "message": assistant.content,
                    "assistantMessage": message,
                }
        user_message = self.chat_messages.get_by_id(turn.user_message_id)
        progress = (user_message.metadata_json or {}).get("chatProgress") if user_message else None
        return progress if isinstance(progress, dict) and progress.get("turnId") == turn.id else _progress_event(turn.id, turn.status)

    def set_feedback(
        self,
        context: CurrentUserContext,
        meeting_id: str,
        message_id: str,
        rating: str,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        meeting = self.meetings.get_for_owner(meeting_id, context.user_id)
        message = self.chat_messages.get_by_id(message_id)
        if meeting is None or message is None or message.meeting_id != meeting_id or message.role != "assistant":
            raise ApplicationError(404, "chat_message_not_found", "Assistant message was not found.")
        if (message.metadata_json or {}).get("evidenceState") not in _FEEDBACK_STATES:
            raise ApplicationError(409, "feedback_not_allowed", "Feedback is not available for this answer.")
        try:
            feedback = self.chat_messages.upsert_feedback(
                message=message,
                user_id=context.user_id,
                rating=rating,
                expected_revision=expected_revision,
            )
        except FeedbackRevisionConflictError as exc:
            raise ApplicationError(409, "feedback_revision_conflict", "Feedback changed in another request. Refresh and try again.") from exc
        self.session.commit()
        return {
            "message_id": message.id,
            "rating": rating,
            "revision": feedback.revision,
            "memory_status": "disabled",
            "cache_action": "disabled",
        }

    def _resolve_turn(self, turn_id: str | None, meeting_id: str | None, user_message_id: str | None, question: str | None):
        if turn_id:
            return self.chat_turns.get(turn_id, for_update=True)
        if user_message_id:
            existing = self.chat_turns.get_by_user_message(user_message_id)
            if existing:
                return existing
            if meeting_id:
                try:
                    return self.chat_turns.create_queued(meeting_id=meeting_id, user_message_id=user_message_id)
                except IntegrityError:
                    self.session.rollback()
                    return self.chat_turns.get_by_user_message(user_message_id)
        if meeting_id and question:
            redacted, found = redact_secrets(question)
            message = self.chat_messages.create(meeting_id=meeting_id, role="user", content=redacted, metadata={"secretRedacted": found})
            return self.chat_turns.create_queued(meeting_id=meeting_id, user_message_id=message.id)
        return None

    def _persist_result(self, turn, meeting, user_message, result: PipelineResult, event_callback: Any) -> dict[str, str]:
        owned = self.chat_turns.claim_for_terminal(turn, expected_lease_token=self.active_lease_token or turn.lease_token)
        if owned is None:
            self.session.rollback()
            return {"status": "processing"}
        trace = redact_structure(result.pipeline_trace)
        stages = list(trace.get("stages", [])) if isinstance(trace, dict) else []
        stages.append({"stage": "persistence", "status": "succeeded", "durationMs": 0, "provider": None, "model": None, "details": {}})
        if isinstance(trace, dict):
            trace["stages"] = stages
        self._emit_pipeline_trace(meeting, turn, trace)
        assistant = self.chat_messages.create(
            meeting_id=meeting.id,
            role="assistant",
            content=result.answer,
            retrieved_chunk_ids=list(result.retrieved_chunk_ids),
            citations=list(result.citations),
            metadata={
                "evidenceState": result.evidence_state,
                "answerOriginKind": result.answer_origin_kind,
                "provider": result.provider,
                "model": result.model,
                "userMessageId": user_message.id,
                "turnId": turn.id,
                "pipelineTrace": trace,
                "querySpec": _query_spec_from_trace(trace),
            },
        )
        terminal = result.terminal_status if result.terminal_status in {"completed", "clarification_needed", "blocked", "error"} else "completed"
        self.chat_turns.mark_terminal(owned, status=terminal, assistant_message_id=assistant.id, error=result.evidence_state if terminal == "error" else None)
        meeting.pending_chat_status = None
        self.session.commit()
        if event_callback:
            if result.answer_origin_kind != "llm_synthesis":
                event_callback(_progress_event(turn.id, "output_policy"))
            event_callback(_progress_event(turn.id, "persistence"))
            event_type = "done" if terminal == "completed" else terminal
            event_callback({
                "type": event_type,
                "turnId": turn.id,
                "answer": result.answer,
                "message": result.answer,
                "assistantMessage": _message_response(assistant).model_dump(mode="json"),
            })
        return {"status": "succeeded" if terminal != "error" else "error", "terminal": terminal}

    def _emit_pipeline_trace(self, meeting, turn, trace: dict[str, Any]) -> None:
        if not isinstance(trace, dict):
            return
        for stage in trace.get("stages", []):
            if not isinstance(stage, dict):
                continue
            status = str(stage.get("status") or "unknown")
            self.operational_logs.emit(
                level="error" if status in {"failed", "blocked"} else "info",
                flow="rag",
                stage=str(stage.get("stage") or "unknown"),
                status=status,
                message=f"Simple RAG stage {stage.get('stage') or 'unknown'} {status}.",
                workspace_id=meeting.owner_user_id,
                meeting_id=meeting.id,
                meeting_name=meeting.title,
                chat={"turnId": turn.id},
                provider=stage.get("provider"),
                model=stage.get("model"),
                executor_type="llm" if stage.get("stage") == "synthesis" else "pipeline",
                duration_ms=stage.get("durationMs") if isinstance(stage.get("durationMs"), int) else None,
                details=stage.get("details") if isinstance(stage.get("details"), dict) else {},
            )


def _query_spec_from_trace(trace: dict[str, Any]) -> dict[str, Any]:
    for stage in trace.get("stages", []):
        if stage.get("stage") == "query_interpretation":
            details = stage.get("details")
            return details.get("querySpec", {}) if isinstance(details, dict) else {}
    return {}


def _turn_status(evidence_state: Any) -> str:
    return evidence_state if evidence_state in {"clarification_needed", "blocked", "error"} else "completed"


def _progress_event(turn_id: str, stage: str) -> dict[str, str]:
    return {
        "type": "status",
        "turnId": turn_id,
        "stage": stage,
        "message": _PROGRESS_MESSAGES.get(stage, "Đang xử lý..."),
    }


def _guardrail_failed(result) -> bool:
    return bool(_GUARDRAIL_FAILURE_CATEGORIES.intersection(result.categories))


def _public_metadata(message: ChatMessage) -> dict[str, Any]:
    internal = message.metadata_json or {}
    result = {
        key: internal[key]
        for key in ("evidenceState", "answerOriginKind", "provider", "model", "pipelineTrace")
        if key in internal
    }
    result["feedbackEligible"] = message.role == "assistant" and internal.get("evidenceState") in _FEEDBACK_STATES
    return redact_structure(result)


def _message_response(message: ChatMessage, feedback=None) -> MeetingChatMessageResponse:
    citations = [MeetingChatCitationResponse(**item) for item in (message.citations or []) if isinstance(item, dict) and item.get("citation_id")]
    return MeetingChatMessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        retrieved_chunk_ids=list(message.retrieved_chunk_ids or []),
        citations=citations,
        metadata=_public_metadata(message),
        feedback_rating=feedback.rating if feedback is not None and feedback.rating in {"up", "down"} else None,
        feedback_revision=feedback.revision if feedback is not None else None,
        created_at=message.created_at,
    )
