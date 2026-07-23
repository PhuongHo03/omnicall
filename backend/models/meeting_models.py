from datetime import datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.configs.database import Base
from backend.models.core_models import utcnow
from backend.models.enums import MeetingAssetKind, MeetingStatus


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    owner_user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[MeetingStatus] = mapped_column(
        Enum(MeetingStatus, name="meeting_status"),
        nullable=False,
        default=MeetingStatus.DRAFT,
        index=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pending_chat_status: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    assets: Mapped[list["MeetingAsset"]] = relationship(back_populates="meeting")


class MeetingAsset(Base):
    __tablename__ = "meeting_assets"
    __table_args__ = (
        UniqueConstraint("object_key", name="uq_meeting_assets_object_key"),
        UniqueConstraint("meeting_id", "idempotency_key", name="uq_meeting_assets_meeting_idempotency"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    owner_user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    meeting_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    kind: Mapped[MeetingAssetKind] = mapped_column(
        Enum(MeetingAssetKind, name="meeting_asset_kind"),
        nullable=False,
        default=MeetingAssetKind.UPLOAD,
    )
    object_key: Mapped[str] = mapped_column(String(700), nullable=False)
    file_name: Mapped[str] = mapped_column(String(260), nullable=False)
    content_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    meeting: Mapped[Meeting | None] = relationship(back_populates="assets")


class MeetingIntelligenceResult(Base):
    __tablename__ = "meeting_intelligence_results"
    __table_args__ = (
        UniqueConstraint("meeting_id", "schema_version", name="uq_meeting_intelligence_result_version"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    meeting_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_model: Mapped[str] = mapped_column(String(180), nullable=False)
    result_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class MeetingTranscriptWindow(Base):
    __tablename__ = "meeting_transcript_windows"
    __table_args__ = (
        UniqueConstraint("meeting_id", "generation", "sequence_no", name="uq_transcript_windows_generation_sequence"),
        UniqueConstraint("meeting_id", "generation", "window_id", name="uq_transcript_windows_generation_window"),
        Index("ix_transcript_windows_meeting_id", "meeting_id"),
        Index("ix_transcript_windows_generation", "generation"),
        Index("ix_transcript_windows_status", "status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    meeting_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    intelligence_result_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("meeting_intelligence_results.id", ondelete="CASCADE"), nullable=True
    )
    generation: Mapped[str] = mapped_column(String(120), nullable=False)
    window_id: Mapped[str] = mapped_column(String(140), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    segment_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    window_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    local_result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class MeetingChunkRecord(Base):
    __tablename__ = "meeting_chunks"
    __table_args__ = (
        UniqueConstraint("meeting_id", "chunk_id", name="uq_meeting_chunks_meeting_chunk"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    meeting_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    intelligence_result_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("meeting_intelligence_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[str] = mapped_column(String(140), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    section_type: Mapped[str] = mapped_column(String(140), nullable=False, index=True)
    source_id: Mapped[str | None] = mapped_column(String(140), nullable=True)
    json_pointer: Mapped[str] = mapped_column(String(500), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    citation_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    segment_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    start_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    visibility: Mapped[str] = mapped_column(String(40), nullable=False, default="workspace")
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


Index(
    "ix_meeting_chunks_text_trgm",
    func.lower(MeetingChunkRecord.text).label("text_lower"),
    postgresql_using="gin",
    postgresql_ops={"text_lower": "gin_trgm_ops"},
)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_meeting_created_id", "meeting_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    meeting_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_chunk_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ChatTurn(Base):
    """Durable unit of work pairing one user question with one terminal answer."""

    __tablename__ = "chat_turns"
    __table_args__ = (
        UniqueConstraint("meeting_id", "sequence_no", name="uq_chat_turns_meeting_sequence"),
        UniqueConstraint("user_message_id", name="uq_chat_turns_user_message"),
        UniqueConstraint("assistant_message_id", name="uq_chat_turns_assistant_message"),
        CheckConstraint(
            "status IN ('queued','started','completed','clarification_needed','blocked','error')",
            name="ck_chat_turns_status",
        ),
        CheckConstraint("sequence_no > 0", name="ck_chat_turns_sequence_positive"),
        CheckConstraint("attempt_count >= 0", name="ck_chat_turns_attempt_nonnegative"),
        CheckConstraint(
            "assistant_message_id IS NULL OR assistant_message_id <> user_message_id",
            name="ck_chat_turns_distinct_messages",
        ),
        Index(
            "uq_chat_turns_one_active_per_meeting",
            "meeting_id",
            unique=True,
            postgresql_where=text("status IN ('queued','started')"),
        ),
        Index("ix_chat_turns_meeting_status", "meeting_id", "status"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    meeting_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    user_message_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False
    )
    assistant_message_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(160), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class MeetingRetrievalSnapshot(Base):
    """Authoritative generation boundary for derived retrieval data."""

    __tablename__ = "meeting_retrieval_snapshots"
    __table_args__ = (
        CheckConstraint("status IN ('building','ready','failed')", name="ck_retrieval_snapshots_status"),
        CheckConstraint("chunk_count >= 0", name="ck_retrieval_snapshots_chunk_count"),
        CheckConstraint(
            "repair_status IN ('none','pending','queued','started')",
            name="ck_retrieval_snapshots_repair_status",
        ),
        CheckConstraint(
            "repair_attempt_count >= 0",
            name="ck_retrieval_snapshots_repair_attempt_count",
        ),
    )

    meeting_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True
    )
    intelligence_result_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("meeting_intelligence_results.id", ondelete="SET NULL"), nullable=True, index=True
    )
    index_generation: Mapped[str] = mapped_column(String(240), nullable=False)
    embedding_identity: Mapped[str] = mapped_column(String(240), nullable=False, default="unknown")
    retrieval_contract: Mapped[str] = mapped_column(String(80), nullable=False, default="v2")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ready", index=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(160), nullable=True)
    repair_status: Mapped[str] = mapped_column(String(16), nullable=False, default="none", index=True)
    repair_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    repair_lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    repair_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    repair_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class ChatMessageFeedback(Base):
    __tablename__ = "chat_message_feedback"
    __table_args__ = (
        UniqueConstraint("chat_message_id", name="uq_chat_message_feedback_message"),
        CheckConstraint("rating IN ('up','down','neutral')", name="ck_chat_message_feedback_rating"),
        CheckConstraint("revision >= 1", name="ck_chat_message_feedback_revision"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    chat_message_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False)
    meeting_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating: Mapped[str] = mapped_column(String(8), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
