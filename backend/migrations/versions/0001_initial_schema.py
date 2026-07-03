"""create the consolidated Omnicall schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    meeting_status = sa.Enum(
        "DRAFT", "UPLOADED", "QUEUED", "PROCESSING", "READY", "FAILED",
        name="meeting_status",
    )
    meeting_asset_kind = sa.Enum(
        "UPLOAD", "RECORDING", "TRANSCRIPT", "EXPORT",
        name="meeting_asset_kind",
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("password_hash", sa.String(length=500), nullable=True),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "account_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_account_sessions_user_id", "account_sessions", ["user_id"])
    op.create_index("ix_account_sessions_token_hash", "account_sessions", ["token_hash"])

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("resource_type", sa.String(length=120), nullable=True),
        sa.Column("resource_id", sa.String(length=160), nullable=True),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_resource_id", "audit_events", ["resource_id"])

    op.create_table(
        "meetings",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("status", meeting_status, nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pending_chat_status", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_meetings_owner_user_id", "meetings", ["owner_user_id"])
    op.create_index("ix_meetings_status", "meetings", ["status"])

    op.create_table(
        "meeting_assets",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("kind", meeting_asset_kind, nullable=False),
        sa.Column("object_key", sa.String(length=700), nullable=False),
        sa.Column("file_name", sa.String(length=260), nullable=False),
        sa.Column("content_type", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key", name="uq_meeting_assets_object_key"),
        sa.UniqueConstraint("meeting_id", "idempotency_key", name="uq_meeting_assets_meeting_idempotency"),
    )
    op.create_index("ix_meeting_assets_owner_user_id", "meeting_assets", ["owner_user_id"])
    op.create_index("ix_meeting_assets_meeting_id", "meeting_assets", ["meeting_id"])

    op.create_table(
        "meeting_intelligence_results",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        sa.Column("provider_name", sa.String(length=120), nullable=False),
        sa.Column("provider_model", sa.String(length=180), nullable=False),
        sa.Column("result_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id", "schema_version", name="uq_meeting_intelligence_result_version"),
    )
    op.create_index("ix_meeting_intelligence_results_meeting_id", "meeting_intelligence_results", ["meeting_id"])

    op.create_table(
        "meeting_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("intelligence_result_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("chunk_id", sa.String(length=140), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("section_type", sa.String(length=140), nullable=False),
        sa.Column("source_id", sa.String(length=140), nullable=True),
        sa.Column("json_pointer", sa.String(length=500), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("citation_ids", postgresql.JSONB(), nullable=False),
        sa.Column("segment_ids", postgresql.JSONB(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=True),
        sa.Column("end_ms", sa.Integer(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", postgresql.JSONB(), nullable=True),
        sa.Column("visibility", sa.String(length=40), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["intelligence_result_id"], ["meeting_intelligence_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id", "chunk_id", name="uq_meeting_chunks_meeting_chunk"),
    )
    op.create_index("ix_meeting_chunks_meeting_id", "meeting_chunks", ["meeting_id"])
    op.create_index("ix_meeting_chunks_intelligence_result_id", "meeting_chunks", ["intelligence_result_id"])
    op.create_index("ix_meeting_chunks_source_type", "meeting_chunks", ["source_type"])
    op.create_index("ix_meeting_chunks_section_type", "meeting_chunks", ["section_type"])

    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("retrieved_chunk_ids", postgresql.JSONB(), nullable=False),
        sa.Column("citations", postgresql.JSONB(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_messages_meeting_id", "chat_messages", ["meeting_id"])
    op.create_index("ix_chat_messages_role", "chat_messages", ["role"])


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("meeting_chunks")
    op.drop_table("meeting_intelligence_results")
    op.drop_table("meeting_assets")
    op.drop_table("meetings")
    op.drop_table("audit_events")
    op.drop_table("account_sessions")
    op.drop_table("users")

    op.execute("DROP TYPE IF EXISTS meeting_asset_kind")
    op.execute("DROP TYPE IF EXISTS meeting_status")
