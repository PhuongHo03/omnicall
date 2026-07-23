"""Retryable worker for the single Simple Evidence-First chat pipeline."""

from __future__ import annotations

import logging

from backend.configs.celery_app import celery_app
from backend.configs.database import SessionLocal
from backend.models.meeting_models import ChatTurn
from backend.providers.chat_event_provider import get_chat_event_provider
from backend.repositories.chat_repository import ChatTurnRepository
from backend.repositories.meeting_repository import MeetingRepository
from backend.services.chat_service import MeetingChatService


logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="omnicall.chat.generate_answer",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
)
def generate_chat_answer(task, *, turn_id: str) -> dict[str, str]:
    with SessionLocal() as session:
        turn = session.get(ChatTurn, turn_id)
        if turn is None:
            return {"status": "error", "error": "chat_turn_not_found"}
        meeting_id = turn.meeting_id
    events = get_chat_event_provider()
    service: MeetingChatService | None = None

    def publish(event: dict) -> None:
        payload = {**event, "turnId": turn_id}
        if service is not None and payload.get("type") == "status":
            service.record_progress(turn_id=turn_id, event=payload)
        try:
            events.publish(f"chat:{meeting_id}", payload)
        except Exception:
            logger.warning("chat.event_publish_failed turn_id=%s", turn_id)

    try:
        with SessionLocal() as session:
            service = MeetingChatService(session)
            return service.generate_answer(turn_id=turn_id, event_callback=publish)
    except Exception as exc:
        logger.exception("chat.generate_answer_failed turn_id=%s", turn_id)
        if task.request.retries < task.max_retries:
            with SessionLocal() as session:
                turn = session.get(ChatTurn, turn_id, with_for_update=True)
                if turn is not None:
                    ChatTurnRepository(session).mark_queued_if_owned(
                        turn,
                        expected_lease_token=service.active_lease_token if service else None,
                        reason=type(exc).__name__,
                    )
                    session.commit()
            raise task.retry(exc=exc, countdown=min(60, 2 ** (task.request.retries + 1))) from exc
        with SessionLocal() as session:
            turn = session.get(ChatTurn, turn_id)
            if turn is not None:
                MeetingChatService(session).save_error_response(
                    meeting_id=turn.meeting_id,
                    user_message_id=turn.user_message_id,
                    turn_id=turn.id,
                    expected_lease_token=service.active_lease_token if service else None,
                )
        publish({"type": "error", "message": "Không thể tạo câu trả lời lúc này. Vui lòng thử lại sau."})
        return {"status": "error", "error": type(exc).__name__}
