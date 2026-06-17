"""add auth sessions account files and audit events

Revision ID: 0006_auth_files_audit
Revises: 0005_chat_history
Create Date: 2026-06-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_auth_files_audit"
down_revision: str | None = "0005_chat_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=500), nullable=True))

    op.create_table(
        "account_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_account_sessions_token_hash"), "account_sessions", ["token_hash"])
    op.create_index(op.f("ix_account_sessions_user_id"), "account_sessions", ["user_id"])
    op.create_index(op.f("ix_account_sessions_workspace_id"), "account_sessions", ["workspace_id"])

    op.create_table(
        "account_files",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("object_key", sa.String(length=700), nullable=False),
        sa.Column("file_name", sa.String(length=260), nullable=False),
        sa.Column("content_type", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["meeting_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key", name="uq_account_files_object_key"),
    )
    op.create_index(op.f("ix_account_files_asset_id"), "account_files", ["asset_id"])
    op.create_index(op.f("ix_account_files_meeting_id"), "account_files", ["meeting_id"])
    op.create_index(op.f("ix_account_files_owner_user_id"), "account_files", ["owner_user_id"])
    op.create_index(op.f("ix_account_files_workspace_id"), "account_files", ["workspace_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("resource_type", sa.String(length=120), nullable=True),
        sa.Column("resource_id", sa.String(length=160), nullable=True),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_events_event_type"), "audit_events", ["event_type"])
    op.create_index(op.f("ix_audit_events_resource_id"), "audit_events", ["resource_id"])
    op.create_index(op.f("ix_audit_events_user_id"), "audit_events", ["user_id"])
    op.create_index(op.f("ix_audit_events_workspace_id"), "audit_events", ["workspace_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_events_workspace_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_user_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_resource_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_event_type"), table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index(op.f("ix_account_files_workspace_id"), table_name="account_files")
    op.drop_index(op.f("ix_account_files_owner_user_id"), table_name="account_files")
    op.drop_index(op.f("ix_account_files_meeting_id"), table_name="account_files")
    op.drop_index(op.f("ix_account_files_asset_id"), table_name="account_files")
    op.drop_table("account_files")

    op.drop_index(op.f("ix_account_sessions_workspace_id"), table_name="account_sessions")
    op.drop_index(op.f("ix_account_sessions_user_id"), table_name="account_sessions")
    op.drop_index(op.f("ix_account_sessions_token_hash"), table_name="account_sessions")
    op.drop_table("account_sessions")

    op.drop_column("users", "password_hash")
