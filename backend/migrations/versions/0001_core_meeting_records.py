"""create core meeting records

Revision ID: 0001_core_meeting_records
Revises:
Create Date: 2026-06-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_core_meeting_records"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


meeting_status = postgresql.ENUM(
    "DRAFT",
    "UPLOADED",
    "QUEUED",
    "PROCESSING",
    "READY",
    "FAILED",
    name="meeting_status",
    create_type=False,
)
meeting_asset_kind = postgresql.ENUM(
    "UPLOAD",
    "RECORDING",
    "TRANSCRIPT",
    "EXPORT",
    name="meeting_asset_kind",
    create_type=False,
)
processing_job_type = postgresql.ENUM(
    "MEETING_PROCESSING",
    name="processing_job_type",
    create_type=False,
)
processing_job_status = postgresql.ENUM(
    "PENDING",
    "RUNNING",
    "RETRYING",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
    name="processing_job_status",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'meeting_status') THEN
                CREATE TYPE meeting_status AS ENUM ('DRAFT', 'UPLOADED', 'QUEUED', 'PROCESSING', 'READY', 'FAILED');
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'meeting_asset_kind') THEN
                CREATE TYPE meeting_asset_kind AS ENUM ('UPLOAD', 'RECORDING', 'TRANSCRIPT', 'EXPORT');
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'processing_job_type') THEN
                CREATE TYPE processing_job_type AS ENUM ('MEETING_PROCESSING');
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'processing_job_status') THEN
                CREATE TYPE processing_job_status AS ENUM ('PENDING', 'RUNNING', 'RETRYING', 'SUCCEEDED', 'FAILED', 'CANCELLED');
            END IF;
        END $$;
        """
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)

    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "workspace_members",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_workspace_user"),
    )
    op.create_index(op.f("ix_workspace_members_user_id"), "workspace_members", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_workspace_members_workspace_id"),
        "workspace_members",
        ["workspace_id"],
        unique=False,
    )

    op.create_table(
        "meetings",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("status", meeting_status, nullable=False),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_meetings_created_by_user_id"), "meetings", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_meetings_status"), "meetings", ["status"], unique=False)
    op.create_index(op.f("ix_meetings_workspace_id"), "meetings", ["workspace_id"], unique=False)

    op.create_table(
        "meeting_assets",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("kind", meeting_asset_kind, nullable=False),
        sa.Column("object_key", sa.String(length=700), nullable=False),
        sa.Column("file_name", sa.String(length=260), nullable=False),
        sa.Column("content_type", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id", "idempotency_key", name="uq_meeting_assets_meeting_idempotency"),
        sa.UniqueConstraint("object_key", name="uq_meeting_assets_object_key"),
    )
    op.create_index(op.f("ix_meeting_assets_created_by_user_id"), "meeting_assets", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_meeting_assets_meeting_id"), "meeting_assets", ["meeting_id"], unique=False)
    op.create_index(op.f("ix_meeting_assets_workspace_id"), "meeting_assets", ["workspace_id"], unique=False)

    op.create_table(
        "processing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("type", processing_job_type, nullable=False),
        sa.Column("status", processing_job_status, nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("safe_failure_reason", sa.Text(), nullable=True),
        sa.Column("internal_error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id", "idempotency_key", name="uq_processing_jobs_meeting_idempotency"),
    )
    op.create_index(op.f("ix_processing_jobs_meeting_id"), "processing_jobs", ["meeting_id"], unique=False)
    op.create_index(op.f("ix_processing_jobs_status"), "processing_jobs", ["status"], unique=False)
    op.create_index(op.f("ix_processing_jobs_workspace_id"), "processing_jobs", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_processing_jobs_workspace_id"), table_name="processing_jobs")
    op.drop_index(op.f("ix_processing_jobs_status"), table_name="processing_jobs")
    op.drop_index(op.f("ix_processing_jobs_meeting_id"), table_name="processing_jobs")
    op.drop_table("processing_jobs")

    op.drop_index(op.f("ix_meeting_assets_workspace_id"), table_name="meeting_assets")
    op.drop_index(op.f("ix_meeting_assets_meeting_id"), table_name="meeting_assets")
    op.drop_index(op.f("ix_meeting_assets_created_by_user_id"), table_name="meeting_assets")
    op.drop_table("meeting_assets")

    op.drop_index(op.f("ix_meetings_workspace_id"), table_name="meetings")
    op.drop_index(op.f("ix_meetings_status"), table_name="meetings")
    op.drop_index(op.f("ix_meetings_created_by_user_id"), table_name="meetings")
    op.drop_table("meetings")

    op.drop_index(op.f("ix_workspace_members_workspace_id"), table_name="workspace_members")
    op.drop_index(op.f("ix_workspace_members_user_id"), table_name="workspace_members")
    op.drop_table("workspace_members")

    op.drop_table("workspaces")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    op.execute("DROP TYPE IF EXISTS processing_job_status")
    op.execute("DROP TYPE IF EXISTS processing_job_type")
    op.execute("DROP TYPE IF EXISTS meeting_asset_kind")
    op.execute("DROP TYPE IF EXISTS meeting_status")
