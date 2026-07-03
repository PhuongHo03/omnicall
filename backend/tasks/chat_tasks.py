from backend.configs.celery_app import celery_app
from backend.configs.database import SessionLocal
from backend.providers.chat_event_provider import get_chat_event_provider
from backend.providers.guardrail_provider import get_guardrail_provider
from backend.providers.llm_provider import get_llm_provider
from backend.services.chat_service import MeetingChatService
from backend.services.operational_log_service import get_operational_log_service
from backend.services.retrieval_search_service import RetrievalSearchService


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

    event_callback({"type": "status", "stage": "started", "message": "Đang xử lý..."})

    with SessionLocal() as session:
        retrieval_search = RetrievalSearchService(session)
        service = MeetingChatService(
            session=session,
            llm_provider=get_llm_provider(),
            retrieval_search=retrieval_search,
            guardrail_provider=get_guardrail_provider(),
            operational_logs=get_operational_log_service(),
        )
        result = service.generate_answer(
            meeting_id=meeting_id,
            user_id=user_id,
            question=question,
            user_message_id=user_message_id,
            input_guardrails=guardrails,
            event_callback=event_callback,
        )

    if result.get("status") == "error":
        event_callback({"type": "error", "message": result.get("error", "Unknown error")})

    return result
