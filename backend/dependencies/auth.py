from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from backend.configs.database import get_db_session
from backend.repositories.auth_repository import AuthRepository
from backend.utils.exceptions import ApplicationError
from backend.utils.security import hash_token


@dataclass(frozen=True)
class CurrentUserContext:
    user_id: str
    role: str


def _validate_uuid(value: str, header_name: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ApplicationError(400, "invalid_auth_context", f"{header_name} must be a UUID.") from exc


def get_current_context(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_user_name: str | None = Header(default=None, alias="X-User-Name"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
    session: Session = Depends(get_db_session),
) -> CurrentUserContext:
    token = _bearer_token(authorization)
    repository = AuthRepository(session)
    if token:
        account_session = repository.get_active_session_by_token_hash(hash_token(token))
        if account_session is None:
            raise ApplicationError(401, "invalid_session", "Session is invalid or expired.")
        user = repository.get_user(account_session.user_id)
        if user is None:
            raise ApplicationError(401, "invalid_session", "Session membership is invalid.")
        return CurrentUserContext(
            user_id=account_session.user_id,
            role=_normalize_role(user.role),
        )

    if not x_user_id:
        raise ApplicationError(
            401,
            "missing_auth_context",
            "X-User-ID header is required.",
        )

    user_id = _validate_uuid(x_user_id, "X-User-ID")
    email = x_user_email or f"{user_id}@local.omnicall"
    display_name = x_user_name or "Local Omnicall User"
    role = _normalize_role(x_user_role or "Admin")

    user = repository.upsert_dev_user(
        user_id=user_id,
        email=email,
        display_name=display_name,
        role=role,
    )
    session.commit()

    return CurrentUserContext(
        user_id=user_id,
        role=_normalize_role(user.role),
    )


def require_admin_context(context: CurrentUserContext = Depends(get_current_context)) -> CurrentUserContext:
    if _normalize_role(context.role) != "Admin":
        raise ApplicationError(403, "admin_access_required", "Admin access is required.")
    return context


def optional_bearer_token(authorization: str | None = Header(default=None, alias="Authorization")) -> str | None:
    return _bearer_token(authorization)


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApplicationError(401, "invalid_authorization_header", "Authorization must use Bearer token.")
    return token


def _normalize_role(role: str) -> str:
    return "Admin" if role.strip().lower() in {"admin", "owner"} else "User"
