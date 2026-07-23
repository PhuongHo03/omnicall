"""Create the consolidated Omnicall schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-26
"""

from collections.abc import Sequence

from alembic import op

from backend import models as _models  # noqa: F401
from backend.configs.database import Base

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
