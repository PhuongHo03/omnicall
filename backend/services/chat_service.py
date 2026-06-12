from uuid import UUID

from sqlalchemy.orm import Session

from backend.dependencies.auth import CurrentUserContext
from backend.dtos.meeting_dto import (
    MeetingChatCitationResponse,
    MeetingChatHistoryResponse,
    MeetingChatMessageResponse,
    MeetingChatRequest,
    MeetingChatResponse,
)
from backend.models.enums import MeetingStatus
from backend.models.meeting_models import ChatMessage, ChatSession, MeetingChunkRecord
from backend.providers.llm_provider import LLMProvider, LLMProviderError, get_llm_provider
from backend.repositories.chat_repository import ChatMessageRepository, ChatSessionRepository
from backend.repositories.meeting_repository import MeetingRepository
from backend.services.retrieval_search_service import RetrievedChunk, RetrievalSearchService
from backend.utils.exceptions import ApplicationError


class MeetingChatService:
    def __init__(
        self,
        session: Session,
        llm_provider: LLMProvider | None = None,
        retrieval_search: RetrievalSearchService | None = None,
    ) -> None:
        self.session = session
        self.meetings = MeetingRepository(session)
        self.chat_sessions = ChatSessionRepository(session)
        self.chat_messages = ChatMessageRepository(session)
        self.retrieval_search = retrieval_search or RetrievalSearchService(session)
        self.llm_provider = llm_provider or get_llm_provider()

    def ask(self, context: CurrentUserContext, meeting_id: str, request: MeetingChatRequest) -> MeetingChatResponse:
        meeting = self.meetings.get_for_workspace(meeting_id, context.workspace_id)
        if meeting is None:
            raise ApplicationError(404, "meeting_not_found", "Meeting was not found.")
        if meeting.status != MeetingStatus.READY:
            raise ApplicationError(409, "meeting_intelligence_not_ready", "Meeting intelligence is not ready for chat.")

        question = request.question.strip()
        if not question:
            raise ApplicationError(400, "empty_question", "Question must not be empty.")

        chat_session = self._resolve_session(
            context=context,
            meeting_id=meeting.id,
            session_id=request.session_id,
            question=question,
        )
        self.chat_messages.create(
            workspace_id=context.workspace_id,
            meeting_id=meeting.id,
            session_id=chat_session.id,
            role="user",
            content=question,
            metadata={"language": request.language or meeting.language},
        )

        retrieved = self.retrieval_search.search_meeting(
            workspace_id=context.workspace_id,
            meeting_id=meeting.id,
            query=question,
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
            answer_payload = self._generate_answer(question=question, retrieved=retrieved)

        assistant = self.chat_messages.create(
            workspace_id=context.workspace_id,
            meeting_id=meeting.id,
            session_id=chat_session.id,
            role="assistant",
            content=answer_payload["answer"],
            retrieved_chunk_ids=[item.record.chunk_id for item in retrieved],
            citations=[citation.model_dump() for citation in citations],
            metadata={
                "evidenceState": answer_payload["evidenceState"],
                "confidence": answer_payload["confidence"],
                "provider": answer_payload["provider"],
            },
        )
        self.session.commit()
        self.session.refresh(assistant)
        return MeetingChatResponse(
            session_id=chat_session.id,
            answer=assistant.content,
            evidence_state=answer_payload["evidenceState"],
            citations=citations,
            message=_message_response(assistant),
        )

    def get_history(self, context: CurrentUserContext, meeting_id: str, session_id: str) -> MeetingChatHistoryResponse:
        meeting = self.meetings.get_for_workspace(meeting_id, context.workspace_id)
        if meeting is None:
            raise ApplicationError(404, "meeting_not_found", "Meeting was not found.")
        chat_session = self._get_session_or_404(
            session_id=session_id,
            workspace_id=context.workspace_id,
            meeting_id=meeting.id,
        )
        messages = self.chat_messages.list_for_session(session_id=chat_session.id)
        return MeetingChatHistoryResponse(
            session_id=chat_session.id,
            meeting_id=meeting.id,
            title=chat_session.title,
            messages=[_message_response(message) for message in messages],
        )

    def _resolve_session(
        self,
        *,
        context: CurrentUserContext,
        meeting_id: str,
        session_id: str | None,
        question: str,
    ) -> ChatSession:
        if session_id:
            return self._get_session_or_404(
                session_id=session_id,
                workspace_id=context.workspace_id,
                meeting_id=meeting_id,
            )
        return self.chat_sessions.create(
            workspace_id=context.workspace_id,
            meeting_id=meeting_id,
            created_by_user_id=context.user_id,
            title=_session_title(question),
        )

    def _get_session_or_404(self, *, session_id: str, workspace_id: str, meeting_id: str) -> ChatSession:
        _validate_uuid(session_id, "chat_session_not_found")
        chat_session = self.chat_sessions.get_for_workspace_meeting(
            session_id=session_id,
            workspace_id=workspace_id,
            meeting_id=meeting_id,
        )
        if chat_session is None:
            raise ApplicationError(404, "chat_session_not_found", "Chat session was not found.")
        return chat_session

    def _generate_answer(self, *, question: str, retrieved: list[RetrievedChunk]) -> dict:
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
            return {
                "answer": answer.strip(),
                "evidenceState": evidence_state,
                "confidence": float(confidence),
                "provider": self.llm_provider.provider_name,
            }
        except LLMProviderError:
            return {
                "answer": _fallback_answer(retrieved),
                "evidenceState": "partial",
                "confidence": 0.45,
                "provider": "local-retrieval-summary",
            }


def _chat_system_prompt() -> str:
    return (
        "You answer questions using only the provided meeting intelligence context. "
        "Return JSON with answer, evidenceState, and confidence. "
        "Use not_enough_evidence when context does not support the answer."
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
        session_id=message.session_id,
        role=message.role,
        content=message.content,
        retrieved_chunk_ids=list(message.retrieved_chunk_ids or []),
        citations=[MeetingChatCitationResponse(**citation) for citation in message.citations],
        metadata=message.metadata_json or {},
        created_at=message.created_at,
    )


def _session_title(question: str) -> str:
    return question[:80] or "Meeting chat"


def _validate_uuid(value: str, error_code: str) -> None:
    try:
        UUID(value)
    except ValueError as exc:
        raise ApplicationError(404, error_code, "Chat session was not found.") from exc
