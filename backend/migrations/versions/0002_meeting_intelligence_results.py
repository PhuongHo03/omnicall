"""create meeting intelligence results

Revision ID: 0002_intel_results
Revises: 0001_core_meeting_records
Create Date: 2026-06-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_intel_results"
down_revision: str | None = "0001_core_meeting_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meeting_intelligence_results",
        sa.Column("id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("processing_job_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        sa.Column("provider_name", sa.String(length=120), nullable=False),
        sa.Column("provider_model", sa.String(length=180), nullable=False),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["processing_job_id"], ["processing_jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id", "schema_version", name="uq_meeting_intelligence_result_version"),
    )
    op.create_index(
        op.f("ix_meeting_intelligence_results_meeting_id"),
        "meeting_intelligence_results",
        ["meeting_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_meeting_intelligence_results_processing_job_id"),
        "meeting_intelligence_results",
        ["processing_job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_meeting_intelligence_results_workspace_id"),
        "meeting_intelligence_results",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_meeting_intelligence_results_workspace_id"), table_name="meeting_intelligence_results")
    op.drop_index(op.f("ix_meeting_intelligence_results_processing_job_id"), table_name="meeting_intelligence_results")
    op.drop_index(op.f("ix_meeting_intelligence_results_meeting_id"), table_name="meeting_intelligence_results")
    op.drop_table("meeting_intelligence_results")
