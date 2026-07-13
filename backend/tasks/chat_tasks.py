import logging

from backend.configs.celery_app import celery_app
from backend.configs.database import SessionLocal
from backend.configs.settings import get_settings
from backend.providers.chat_event_provider import get_chat_event_provider
from backend.providers.guardrail_provider import get_guardrail_provider
from backend.providers.llm import get_llm_provider
from backend.services.chat_service import MeetingChatService
from backend.services.operational_log_service import get_operational_log_service
from backend.services.retrieval.search_service import RetrievalSearchService
from backend.repositories.chat_repository import ChatMessageRepository
from backend.repositories.meeting_repository import MeetingRepository

logger = logging.getLogger(__name__)


def _chat_channel(meeting_id: str) -> str:
    return f"chat:{meeting_id}"


@celery_app.task(
    name="omnicall.chat.generate_answer",
    acks_late=True,
    reject_on_worker_lost=True,
)
def generate_chat_answer(
    meeting_id: str,
    user_id: str,
    question: str,
    user_message_id: str,
    guardrails: dict,
) -> dict[str, str]:
    event_provider = get_chat_event_provider()
    channel = _chat_channel(meeting_id)

    def event_callback(event):
        event_provider.publish(channel, event)

    settings = get_settings()

    # Emit initial status
    event_callback({"type": "status", "stage": "started", "message": "Đang xử lý..."})

    try:
        with SessionLocal() as session:
            retrieval_search = RetrievalSearchService(session)
            llm_provider = get_llm_provider()

            from backend.services.agent import AgenticRAGService
            agentic_rag_service = AgenticRAGService(
                session=session,
                llm_provider=llm_provider,
                retrieval_search=retrieval_search,
                operational_logs=get_operational_log_service(),
                settings=settings,
                max_iterations=settings.agentic_rag_max_iterations,
                iteration_timeout_seconds=settings.agentic_rag_iteration_timeout_seconds,
                total_timeout_seconds=settings.agentic_rag_total_timeout_seconds,
                max_replans=settings.agentic_rag_max_replans,
                max_tool_calls_per_iteration=settings.agentic_rag_max_tool_calls_per_iteration,
                max_chunks_per_tool=settings.agentic_rag_max_chunks_per_tool,
                max_total_chunks=settings.agentic_rag_max_total_chunks,
                session_factory=SessionLocal,
            )

            service = MeetingChatService(
                session=session,
                llm_provider=llm_provider,
                retrieval_search=retrieval_search,
                guardrail_provider=get_guardrail_provider(),
                operational_logs=get_operational_log_service(),
                agentic_rag_service=agentic_rag_service,
            )

            result = service.generate_answer(
                meeting_id=meeting_id,
                user_id=user_id,
                question=question,
                user_message_id=user_message_id,
                input_guardrails=guardrails,
                event_callback=event_callback,
            )
    except Exception as exc:
        logger.exception("chat.generate_answer_failed meeting_id=%s user_message_id=%s", meeting_id, user_message_id)
        try:
            get_operational_log_service().emit(
                level="error",
                flow="rag",
                stage="answer",
                status="failed",
                message="Chat answer generation failed and an error response was persisted.",
                workspace_id=user_id,
                meeting_id=meeting_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
        except Exception:
            logger.exception("chat.failure_log_emit_failed meeting_id=%s", meeting_id)
        with SessionLocal() as session:
            meeting = MeetingRepository(session).get_for_owner(meeting_id, user_id)
            if meeting is not None:
                meeting.pending_chat_status = None
                chat_messages = ChatMessageRepository(session)
                if chat_messages.get_response_for_user_message(
                    meeting_id=meeting_id,
                    user_message_id=user_message_id,
                ) is None:
                    chat_messages.create(
                        meeting_id=meeting_id,
                        role="assistant",
                        content="Không thể tạo câu trả lời lúc này. Vui lòng thử lại sau.",
                        metadata={
                            "evidenceState": "error",
                            "confidence": 0.0,
                            "provider": "system",
                            "userMessageId": user_message_id,
                            "guardrails": {},
                        },
                    )
                session.commit()
        try:
            event_callback({"type": "error", "message": "Không thể tạo câu trả lời lúc này. Vui lòng thử lại sau."})
        except Exception:
            logger.exception("chat.error_event_publish_failed meeting_id=%s", meeting_id)
        return {"status": "error", "error": type(exc).__name__}

    if result.get("status") == "error":
        event_callback({"type": "error", "message": result.get("error", "Lỗi không xác định")})

    return result
