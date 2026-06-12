from sqlalchemy import asc, select
from sqlalchemy.orm import Session

from backend.models.meeting_models import ChatMessage, ChatSession


class ChatSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        created_by_user_id: str,
        title: str,
    ) -> ChatSession:
        chat_session = ChatSession(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            created_by_user_id=created_by_user_id,
            title=title,
        )
        self.session.add(chat_session)
        self.session.flush()
        return chat_session

    def get_for_workspace_meeting(
        self,
        *,
        session_id: str,
        workspace_id: str,
        meeting_id: str,
    ) -> ChatSession | None:
        statement = select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.workspace_id == workspace_id,
            ChatSession.meeting_id == meeting_id,
        )
        return self.session.scalars(statement).first()


class ChatMessageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        session_id: str,
        role: str,
        content: str,
        retrieved_chunk_ids: list[str] | None = None,
        citations: list[dict] | None = None,
        metadata: dict | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            session_id=session_id,
            role=role,
            content=content,
            retrieved_chunk_ids=retrieved_chunk_ids or [],
            citations=citations or [],
            metadata_json=metadata or {},
        )
        self.session.add(message)
        self.session.flush()
        return message

    def list_for_session(self, *, session_id: str) -> list[ChatMessage]:
        statement = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(asc(ChatMessage.created_at), asc(ChatMessage.id))
        )
        return list(self.session.scalars(statement).all())
