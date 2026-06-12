"""create meeting retrieval chunks

Revision ID: 0004_meeting_chunks
Revises: 0003_intel_indexes
Create Date: 2026-06-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_meeting_chunks"
down_revision: str | None = "0003_intel_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meeting_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("intelligence_result_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("chunk_id", sa.String(length=140), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("section_type", sa.String(length=140), nullable=False),
        sa.Column("source_id", sa.String(length=140), nullable=True),
        sa.Column("json_pointer", sa.String(length=500), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("citation_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("segment_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=True),
        sa.Column("end_ms", sa.Integer(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("visibility", sa.String(length=40), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["intelligence_result_id"], ["meeting_intelligence_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id", "chunk_id", name="uq_meeting_chunks_meeting_chunk"),
    )
    op.create_index(op.f("ix_meeting_chunks_intelligence_result_id"), "meeting_chunks", ["intelligence_result_id"])
    op.create_index(op.f("ix_meeting_chunks_meeting_id"), "meeting_chunks", ["meeting_id"])
    op.create_index(op.f("ix_meeting_chunks_section_type"), "meeting_chunks", ["section_type"])
    op.create_index(op.f("ix_meeting_chunks_source_type"), "meeting_chunks", ["source_type"])
    op.create_index(op.f("ix_meeting_chunks_workspace_id"), "meeting_chunks", ["workspace_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_meeting_chunks_workspace_id"), table_name="meeting_chunks")
    op.drop_index(op.f("ix_meeting_chunks_source_type"), table_name="meeting_chunks")
    op.drop_index(op.f("ix_meeting_chunks_section_type"), table_name="meeting_chunks")
    op.drop_index(op.f("ix_meeting_chunks_meeting_id"), table_name="meeting_chunks")
    op.drop_index(op.f("ix_meeting_chunks_intelligence_result_id"), table_name="meeting_chunks")
    op.drop_table("meeting_chunks")
