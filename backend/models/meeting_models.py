from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
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


class ChatMessage(Base):
    __tablename__ = "chat_messages"

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
