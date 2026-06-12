from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from backend.configs.database import get_db_session
from backend.repositories.auth_repository import AuthRepository
from backend.utils.exceptions import ApplicationError


@dataclass(frozen=True)
class CurrentUserContext:
    user_id: str
    workspace_id: str
    role: str


def _validate_uuid(value: str, header_name: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ApplicationError(400, "invalid_auth_context", f"{header_name} must be a UUID.") from exc


def get_current_context(
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    x_workspace_id: str | None = Header(default=None, alias="X-Workspace-ID"),
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_user_name: str | None = Header(default=None, alias="X-User-Name"),
    x_workspace_name: str | None = Header(default=None, alias="X-Workspace-Name"),
    session: Session = Depends(get_db_session),
) -> CurrentUserContext:
    if not x_user_id or not x_workspace_id:
        raise ApplicationError(
            401,
            "missing_auth_context",
            "X-User-ID and X-Workspace-ID headers are required.",
        )

    user_id = _validate_uuid(x_user_id, "X-User-ID")
    workspace_id = _validate_uuid(x_workspace_id, "X-Workspace-ID")
    email = x_user_email or f"{user_id}@local.omnicall"
    display_name = x_user_name or "Local Omnicall User"
    workspace_name = x_workspace_name or "Local Omnicall Workspace"

    repository = AuthRepository(session)
    membership = repository.upsert_dev_context(
        user_id=user_id,
        workspace_id=workspace_id,
        email=email,
        display_name=display_name,
        workspace_name=workspace_name,
    )
    session.commit()

    return CurrentUserContext(
        user_id=user_id,
        workspace_id=workspace_id,
        role=membership.role,
    )
