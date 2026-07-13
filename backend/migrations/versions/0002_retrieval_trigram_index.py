"""Add PostgreSQL trigram support for degraded retrieval fallback."""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_retrieval_trigram_index"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_meeting_chunks_text_trgm "
        "ON meeting_chunks USING gin (lower(text) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_meeting_chunks_text_trgm")
