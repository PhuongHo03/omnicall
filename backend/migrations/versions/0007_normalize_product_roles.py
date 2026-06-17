"""normalize product roles

Revision ID: 0007_normalize_product_roles
Revises: 0006_auth_files_audit
Create Date: 2026-06-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_normalize_product_roles"
down_revision: str | None = "0006_auth_files_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE workspace_members
        SET role = CASE
            WHEN lower(role) IN ('admin', 'owner') THEN 'Admin'
            WHEN lower(role) = 'user' THEN 'User'
            ELSE 'User'
        END
        """
    )
    op.execute(
        """
        UPDATE account_sessions
        SET role = CASE
            WHEN lower(role) IN ('admin', 'owner') THEN 'Admin'
            WHEN lower(role) = 'user' THEN 'User'
            ELSE 'User'
        END
        """
    )
    op.create_check_constraint(
        "ck_workspace_members_product_role",
        "workspace_members",
        "role IN ('Admin', 'User')",
    )
    op.create_check_constraint(
        "ck_account_sessions_product_role",
        "account_sessions",
        "role IN ('Admin', 'User')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_account_sessions_product_role", "account_sessions", type_="check")
    op.drop_constraint("ck_workspace_members_product_role", "workspace_members", type_="check")
