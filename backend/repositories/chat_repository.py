from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.orm import Session

from backend.models.meeting_models import ChatMessage, ChatMessageFeedback, ChatTurn, Meeting


TERMINAL_CHAT_TURN_STATUSES = {
    "completed", "clarification_needed", "blocked", "error",
}


class FeedbackRevisionConflictError(RuntimeError):
    pass


class ChatMessageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        meeting_id: str,
        role: str,
        content: str,
        retrieved_chunk_ids: list[str] | None = None,
        citations: list[dict] | None = None,
        metadata: dict | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            meeting_id=meeting_id,
            role=role,
            content=content,
            retrieved_chunk_ids=retrieved_chunk_ids or [],
            citations=citations or [],
            metadata_json=metadata or {},
        )
        self.session.add(message)
        self.session.flush()
        return message

    def get_by_id(self, message_id: str) -> ChatMessage | None:
        return self.session.get(ChatMessage, message_id)

    def list_by_ids(self, message_ids: list[str]) -> list[ChatMessage]:
        if not message_ids:
            return []
        return list(
            self.session.scalars(
                select(ChatMessage).where(ChatMessage.id.in_(message_ids))
            ).all()
        )

    def update(
        self,
        message: ChatMessage,
        *,
        content: str | None = None,
        metadata: dict | None = None,
    ) -> ChatMessage:
        if content is not None:
            message.content = content
        if metadata is not None:
            message.metadata_json = metadata
        self.session.flush()
        return message

    def list_for_meeting(self, *, meeting_id: str) -> list[ChatMessage]:
        statement = (
            select(ChatMessage)
            .where(ChatMessage.meeting_id == meeting_id)
            .order_by(asc(ChatMessage.created_at), asc(ChatMessage.id))
        )
        return list(self.session.scalars(statement).all())

    def get_response_for_user_message(self, *, meeting_id: str, user_message_id: str) -> ChatMessage | None:
        """Return an existing terminal assistant response for one user message."""
        turn = self.session.scalar(
            select(ChatTurn).where(
                ChatTurn.meeting_id == meeting_id,
                ChatTurn.user_message_id == user_message_id,
            )
        )
        if turn is not None and turn.assistant_message_id:
            return self.get_by_id(turn.assistant_message_id)
        for message in self.list_for_meeting(meeting_id=meeting_id):
            metadata = message.metadata_json or {}
            if (
                message.role == "assistant"
                and metadata.get("userMessageId") == user_message_id
            ):
                return message
        return None

    def list_completed_before(self, *, meeting_id: str, before_message_id: str, limit: int) -> list[ChatMessage]:
        """Return paired, complete prior turns for prompt context, oldest first."""
        before = self.get_by_id(before_message_id)
        if before is None:
            return []
        before_turn = self.session.scalar(
            select(ChatTurn).where(ChatTurn.user_message_id == before_message_id)
        )
        if before_turn is not None:
            turns = list(
                self.session.scalars(
                    select(ChatTurn)
                    .where(
                        ChatTurn.meeting_id == meeting_id,
                        ChatTurn.sequence_no < before_turn.sequence_no,
                        ChatTurn.status == "completed",
                        ChatTurn.assistant_message_id.is_not(None),
                    )
                    .order_by(desc(ChatTurn.sequence_no))
                    .limit(max(0, limit))
                ).all()
            )
            turns.reverse()
            message_ids = [
                message_id
                for turn in turns
                for message_id in (turn.user_message_id, turn.assistant_message_id)
                if message_id
            ]
            if not message_ids:
                return []
            messages = list(self.session.scalars(select(ChatMessage).where(ChatMessage.id.in_(message_ids))).all())
            by_id = {message.id: message for message in messages}
            return [by_id[message_id] for message_id in message_ids if message_id in by_id]

        # Compatibility for data created before Phase 44. Filtering happens
        # before limiting, so pending/error messages cannot hide older turns.
        statement = (
            select(ChatMessage)
            .where(
                ChatMessage.meeting_id == meeting_id,
                ChatMessage.created_at <= before.created_at,
                ChatMessage.id != before_message_id,
            )
            .order_by(asc(ChatMessage.created_at), asc(ChatMessage.id))
        )
        candidates = list(self.session.scalars(statement).all())
        users = {message.id: message for message in candidates if message.role == "user"}
        pairs: list[tuple[ChatMessage, ChatMessage]] = []
        for assistant in candidates:
            metadata = assistant.metadata_json or {}
            user_id = metadata.get("userMessageId")
            if (
                assistant.role != "assistant"
                or metadata.get("evidenceState") in {"error", "blocked", "clarification_needed"}
                or metadata.get("pending")
                or not isinstance(user_id, str)
                or user_id not in users
            ):
                continue
            pairs.append((users[user_id], assistant))
        pairs = pairs[-max(0, limit):]
        return [message for pair in pairs for message in pair]

    def count_prior_user_messages(self, *, meeting_id: str, before_message_id: str) -> int:
        return sum(1 for item in self.list_completed_before(meeting_id=meeting_id, before_message_id=before_message_id, limit=1000) if item.role == "user")

    def get_feedback(self, message_id: str) -> ChatMessageFeedback | None:
        return self.session.scalar(select(ChatMessageFeedback).where(ChatMessageFeedback.chat_message_id == message_id))

    def feedback_by_message_ids(self, message_ids: list[str]) -> dict[str, ChatMessageFeedback]:
        if not message_ids:
            return {}
        rows = self.session.scalars(
            select(ChatMessageFeedback).where(ChatMessageFeedback.chat_message_id.in_(message_ids))
        ).all()
        return {item.chat_message_id: item for item in rows}

    def upsert_feedback(
        self,
        *,
        message: ChatMessage,
        user_id: str,
        rating: str,
        expected_revision: int | None = None,
    ) -> ChatMessageFeedback:
        # The parent message always exists and provides a stable lock even
        # before the first feedback row has been inserted. This serializes two
        # concurrent first writes that SELECT FOR UPDATE on a missing feedback
        # row alone cannot protect.
        self.session.scalar(
            select(ChatMessage)
            .where(ChatMessage.id == message.id)
            .with_for_update()
        )
        feedback = self.session.scalar(
            select(ChatMessageFeedback)
            .where(ChatMessageFeedback.chat_message_id == message.id)
            .with_for_update()
        )
        current_revision = feedback.revision if feedback is not None else 0
        if expected_revision is not None and expected_revision != current_revision:
            raise FeedbackRevisionConflictError(
                f"Expected feedback revision {expected_revision}, found {current_revision}."
            )
        if feedback is None:
            feedback = ChatMessageFeedback(
                chat_message_id=message.id,
                meeting_id=message.meeting_id,
                user_id=user_id,
                rating=rating,
                revision=1,
            )
            self.session.add(feedback)
        else:
            feedback.revision += 1
            feedback.rating = rating
            feedback.user_id = user_id
        self.session.flush()
        return feedback

    def delete_feedback(self, message_id: str) -> bool:
        feedback = self.get_feedback(message_id)
        if feedback is None:
            return False
        self.session.delete(feedback)
        self.session.flush()
        return True



class ChatTurnRepository:
    """Persistence boundary for durable, idempotent chat work."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def lock_meeting(self, meeting_id: str) -> Meeting | None:
        return self.session.scalar(
            select(Meeting)
            .where(Meeting.id == meeting_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def create_queued(self, *, meeting_id: str, user_message_id: str) -> ChatTurn:
        # Serializing on the meeting row gives deterministic sequence numbers;
        # the partial unique index remains the final concurrency invariant.
        self.lock_meeting(meeting_id)
        next_sequence = int(
            self.session.scalar(
                select(func.coalesce(func.max(ChatTurn.sequence_no), 0) + 1).where(
                    ChatTurn.meeting_id == meeting_id
                )
            )
            or 1
        )
        turn = ChatTurn(
            meeting_id=meeting_id,
            sequence_no=next_sequence,
            user_message_id=user_message_id,
            status="queued",
        )
        self.session.add(turn)
        self.session.flush()
        return turn

    def get(self, turn_id: str, *, for_update: bool = False) -> ChatTurn | None:
        statement = select(ChatTurn).where(ChatTurn.id == turn_id)
        if for_update:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return self.session.scalar(statement)

    def list_by_ids(self, turn_ids: list[str]) -> list[ChatTurn]:
        if not turn_ids:
            return []
        return list(
            self.session.scalars(
                select(ChatTurn).where(ChatTurn.id.in_(turn_ids))
            ).all()
        )

    def get_by_user_message(self, user_message_id: str) -> ChatTurn | None:
        return self.session.scalar(select(ChatTurn).where(ChatTurn.user_message_id == user_message_id))

    def immediately_previous(self, turn: ChatTurn) -> ChatTurn | None:
        """Return only the adjacent prior turn; never revive stale state."""

        if turn.sequence_no <= 1:
            return None
        return self.session.scalar(
            select(ChatTurn).where(
                ChatTurn.meeting_id == turn.meeting_id,
                ChatTurn.sequence_no == turn.sequence_no - 1,
            )
        )

    def active_for_meeting(self, meeting_id: str) -> ChatTurn | None:
        return self.session.scalar(
            select(ChatTurn).where(
                ChatTurn.meeting_id == meeting_id,
                ChatTurn.status.in_(("queued", "started")),
            )
        )

    def mark_started(self, turn: ChatTurn, *, lease_seconds: int = 300) -> ChatTurn:
        if turn.status == "queued":
            turn.status = "started"
            turn.attempt_count += 1
            turn.started_at = datetime.now(UTC)
            turn.lease_token = str(uuid4())
            turn.lease_expires_at = datetime.now(UTC) + timedelta(seconds=max(30, lease_seconds))
            turn.last_error = None
            self.session.flush()
        return turn

    def mark_queued(self, turn: ChatTurn, *, reason: str | None = None) -> ChatTurn:
        """Make an interrupted non-terminal turn claimable again."""
        if turn.status not in {"queued", "started"}:
            return turn
        turn.status = "queued"
        turn.started_at = None
        turn.lease_token = None
        turn.lease_expires_at = None
        turn.last_error = reason[:160] if reason else None
        self.session.flush()
        return turn

    def mark_queued_if_owned(
        self,
        turn: ChatTurn,
        *,
        expected_lease_token: str | None,
        reason: str | None = None,
    ) -> bool:
        """Requeue only the worker lease that experienced the failure."""
        fresh = self.get(turn.id, for_update=True)
        if (
            fresh is None
            or fresh.status != "started"
            or not expected_lease_token
            or fresh.lease_token != expected_lease_token
        ):
            return False
        self.mark_queued(fresh, reason=reason)
        return True

    def refresh_lease(
        self,
        turn: ChatTurn,
        *,
        lease_seconds: int = 300,
        expected_lease_token: str | None = None,
    ) -> bool:
        # Capture the caller's token before populate_existing refreshes the ORM
        # identity. Otherwise ``turn`` and ``fresh`` are the same object and a
        # stale worker could accidentally adopt a reconciler/takeover token.
        expected_token = expected_lease_token or turn.lease_token
        fresh = self.get(turn.id, for_update=True)
        if (
            fresh is None
            or fresh.status != "started"
            or not expected_token
            or fresh.lease_token != expected_token
        ):
            return False
        fresh.lease_expires_at = datetime.now(UTC) + timedelta(seconds=max(30, lease_seconds))
        self.session.flush()
        return True

    def claim_for_terminal(
        self,
        turn: ChatTurn,
        *,
        expected_lease_token: str | None = None,
    ) -> ChatTurn | None:
        # As with refresh_lease(), do not infer ownership from an ORM object
        # that may have been expired and refreshed after another worker took
        # over the turn. Callers that started the work pass the token they
        # originally claimed.
        expected_token = expected_lease_token or turn.lease_token
        fresh = self.get(turn.id, for_update=True)
        if (
            fresh is None
            or fresh.status != "started"
            or not expected_token
            or fresh.lease_token != expected_token
        ):
            return None
        return fresh

    def mark_terminal(
        self,
        turn: ChatTurn,
        *,
        status: str,
        assistant_message_id: str | None,
        error: str | None = None,
    ) -> ChatTurn:
        if status not in TERMINAL_CHAT_TURN_STATUSES:
            raise ValueError(f"Invalid terminal chat turn status: {status}")
        turn.status = status
        turn.assistant_message_id = assistant_message_id
        turn.last_error = error[:160] if error else None
        turn.lease_token = None
        turn.lease_expires_at = None
        turn.completed_at = datetime.now(UTC)
        self.session.flush()
        return turn

    def list_stale_active(self, *, updated_before: datetime, limit: int) -> list[ChatTurn]:
        return list(
            self.session.scalars(
                select(ChatTurn)
                .where(
                    or_(
                        and_(ChatTurn.status == "queued", ChatTurn.updated_at < updated_before),
                        and_(
                            ChatTurn.status == "started",
                            or_(
                                ChatTurn.lease_expires_at.is_(None),
                                ChatTurn.lease_expires_at < datetime.now(UTC),
                            ),
                        ),
                    ),
                )
                .order_by(asc(ChatTurn.updated_at), asc(ChatTurn.id))
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
        )
