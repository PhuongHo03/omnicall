from sqlalchemy import asc, select
from sqlalchemy.orm import Session

from backend.models.meeting_models import ChatMessage


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
        for message in self.list_for_meeting(meeting_id=meeting_id):
            metadata = message.metadata_json or {}
            if (
                message.role == "assistant"
                and metadata.get("userMessageId") == user_message_id
            ):
                return message
        return None
