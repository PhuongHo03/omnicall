"""create meeting intelligence derived indexes

Revision ID: 0003_intel_indexes
Revises: 0002_intel_results
Create Date: 2026-06-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_intel_indexes"
down_revision: str | None = "0002_intel_results"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transcript_segments",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("intelligence_result_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("segment_id", sa.String(length=80), nullable=False),
        sa.Column("speaker", sa.String(length=160), nullable=True),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["intelligence_result_id"], ["meeting_intelligence_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id", "segment_id", name="uq_transcript_segments_meeting_segment"),
    )
    op.create_index(op.f("ix_transcript_segments_intelligence_result_id"), "transcript_segments", ["intelligence_result_id"])
    op.create_index(op.f("ix_transcript_segments_meeting_id"), "transcript_segments", ["meeting_id"])
    op.create_index(op.f("ix_transcript_segments_workspace_id"), "transcript_segments", ["workspace_id"])

    op.create_table(
        "meeting_insights",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("intelligence_result_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("section", sa.String(length=120), nullable=False),
        sa.Column("item_id", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("citation_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("segment_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["intelligence_result_id"], ["meeting_intelligence_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id", "section", "item_id", name="uq_meeting_insights_meeting_section_item"),
    )
    op.create_index(op.f("ix_meeting_insights_intelligence_result_id"), "meeting_insights", ["intelligence_result_id"])
    op.create_index(op.f("ix_meeting_insights_meeting_id"), "meeting_insights", ["meeting_id"])
    op.create_index(op.f("ix_meeting_insights_section"), "meeting_insights", ["section"])
    op.create_index(op.f("ix_meeting_insights_workspace_id"), "meeting_insights", ["workspace_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_meeting_insights_workspace_id"), table_name="meeting_insights")
    op.drop_index(op.f("ix_meeting_insights_section"), table_name="meeting_insights")
    op.drop_index(op.f("ix_meeting_insights_meeting_id"), table_name="meeting_insights")
    op.drop_index(op.f("ix_meeting_insights_intelligence_result_id"), table_name="meeting_insights")
    op.drop_table("meeting_insights")
    op.drop_index(op.f("ix_transcript_segments_workspace_id"), table_name="transcript_segments")
    op.drop_index(op.f("ix_transcript_segments_meeting_id"), table_name="transcript_segments")
    op.drop_index(op.f("ix_transcript_segments_intelligence_result_id"), table_name="transcript_segments")
    op.drop_table("transcript_segments")
