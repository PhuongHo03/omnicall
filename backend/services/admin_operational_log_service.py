from typing import Any

from sqlalchemy.orm import Session

from backend.repositories.chat_repository import ChatMessageRepository, ChatTurnRepository
from backend.services.operational_log_service import OperationalLogService

_TERMINAL_ANSWER_STATUSES = {"succeeded", "failed", "blocked"}


class AdminOperationalLogService:
    """Hydrate transient operational events from durable chat records for admins."""

    def __init__(
        self,
        session: Session,
        operational_logs: OperationalLogService,
        *,
        chat_messages: ChatMessageRepository | None = None,
        chat_turns: ChatTurnRepository | None = None,
    ) -> None:
        self.operational_logs = operational_logs
        self.chat_messages = chat_messages or ChatMessageRepository(session)
        self.chat_turns = chat_turns or ChatTurnRepository(session)

    def tail(
        self,
        *,
        limit: int,
        flow: str | None = None,
        level: str | None = None,
        search: str | None = None,
        meeting_id: str | None = None,
    ) -> list[dict[str, Any]]:
        events = self.operational_logs.tail(
            limit=limit,
            flow=flow,
            level=level,
            search=search,
            meeting_id=meeting_id,
        )
        return self._hydrate_chat(events)

    def _hydrate_chat(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        turn_ids = {
            turn_id
            for event in events
            if (turn_id := _event_turn_id(event)) is not None
        }
        turns = self.chat_turns.list_by_ids(list(turn_ids))
        turns_by_id = {turn.id: turn for turn in turns}
        message_ids = {
            message_id
            for turn in turns
            for message_id in (turn.user_message_id, turn.assistant_message_id)
            if message_id
        }
        messages = self.chat_messages.list_by_ids(list(message_ids))
        messages_by_id = {message.id: message for message in messages}

        hydrated: list[dict[str, Any]] = []
        for stored_event in events:
            event = dict(stored_event)
            chat = dict(event.get("chat") or {})
            turn_id = _event_turn_id(event)
            turn = turns_by_id.get(turn_id) if turn_id else None
            if turn is not None and (
                not event.get("meetingId") or turn.meeting_id == event.get("meetingId")
            ):
                chat["turnId"] = turn.id
                chat["userMessageId"] = turn.user_message_id
                question = messages_by_id.get(turn.user_message_id)
                if question is not None and question.role == "user":
                    chat["question"] = question.content
                if _is_terminal_answer_event(event) and turn.assistant_message_id:
                    chat["assistantMessageId"] = turn.assistant_message_id
                    answer = messages_by_id.get(turn.assistant_message_id)
                    if answer is not None and answer.role == "assistant":
                        chat["answer"] = answer.content
            event["chat"] = chat
            hydrated.append(event)
        return hydrated


def _event_turn_id(event: dict[str, Any]) -> str | None:
    chat = event.get("chat") if isinstance(event.get("chat"), dict) else {}
    details = event.get("details") if isinstance(event.get("details"), dict) else {}
    turn_id = chat.get("turnId") or details.get("turnId")
    return turn_id if isinstance(turn_id, str) and turn_id else None


def _is_terminal_answer_event(event: dict[str, Any]) -> bool:
    return (
        event.get("flow") == "rag"
        and event.get("stage") == "answer"
        and event.get("status") in _TERMINAL_ANSWER_STATUSES
    )
