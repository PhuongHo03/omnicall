"""Persist bounded transcript windows and their local extraction state."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0003_transcript_windows"
down_revision: str | None = "0002_retrieval_trigram_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meeting_transcript_windows",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("intelligence_result_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("generation", sa.String(length=120), nullable=False),
        sa.Column("window_id", sa.String(length=140), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=True),
        sa.Column("end_ms", sa.Integer(), nullable=True),
        sa.Column("segment_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("window_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("local_result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["intelligence_result_id"], ["meeting_intelligence_results.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id", "generation", "sequence_no", name="uq_transcript_windows_generation_sequence"),
        sa.UniqueConstraint("meeting_id", "generation", "window_id", name="uq_transcript_windows_generation_window"),
    )
    op.create_index("ix_transcript_windows_meeting_id", "meeting_transcript_windows", ["meeting_id"])
    op.create_index("ix_transcript_windows_generation", "meeting_transcript_windows", ["generation"])
    op.create_index("ix_transcript_windows_status", "meeting_transcript_windows", ["status"])


def downgrade() -> None:
    op.drop_index("ix_transcript_windows_status", table_name="meeting_transcript_windows")
    op.drop_index("ix_transcript_windows_generation", table_name="meeting_transcript_windows")
    op.drop_index("ix_transcript_windows_meeting_id", table_name="meeting_transcript_windows")
    op.drop_table("meeting_transcript_windows")
