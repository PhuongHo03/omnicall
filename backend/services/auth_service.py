from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.configs.settings import Settings, get_settings
from backend.dependencies.auth import CurrentUserContext
from backend.dtos.auth_dto import (
    AccountResponse,
    AuthLoginRequest,
    AuthRegisterRequest,
    AuthSessionResponse,
    MeResponse,
)
from backend.models.core_models import User, WorkspaceMember
from backend.repositories.auth_repository import AuditEventRepository, AuthRepository
from backend.utils.exceptions import ApplicationError
from backend.utils.security import hash_password, hash_token, new_session_token, verify_password


class AuthService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.auth = AuthRepository(session)
        self.audit = AuditEventRepository(session)

    def register(self, request: AuthRegisterRequest) -> AuthSessionResponse:
        email = request.email.strip().lower()
        if "@" not in email:
            raise ApplicationError(400, "invalid_email", "A valid email is required.")
        if self.auth.get_user_by_email(email) is not None:
            raise ApplicationError(409, "account_exists", "An account already exists for this email.")
        role = _normalize_product_role(request.role)
        membership = self.auth.create_account(
            email=email,
            display_name=request.display_name.strip(),
            password_hash=hash_password(request.password),
            role=role,
            workspace_name=(request.workspace_name or f"{request.display_name.strip()} Workspace").strip(),
        )
        self.audit.create(
            event_type="auth.register",
            outcome="success",
            workspace_id=membership.workspace_id,
            user_id=membership.user_id,
            resource_type="user",
            resource_id=membership.user_id,
            metadata={"role": role},
        )
        response = self._create_session_response(membership)
        self.session.commit()
        return response

    def login(self, request: AuthLoginRequest) -> AuthSessionResponse:
        user = self.auth.get_user_by_email(request.email.strip().lower())
        if user is None or not verify_password(request.password, user.password_hash):
            self.audit.create(event_type="auth.login", outcome="failure", metadata={"email": request.email.strip().lower()})
            self.session.commit()
            raise ApplicationError(401, "invalid_credentials", "Email or password is incorrect.")
        membership = _first_membership(user)
        if membership is None:
            raise ApplicationError(403, "missing_membership", "Account is not assigned to a workspace.")
        self.audit.create(
            event_type="auth.login",
            outcome="success",
            workspace_id=membership.workspace_id,
            user_id=user.id,
            resource_type="user",
            resource_id=user.id,
            metadata={"role": _normalize_product_role(membership.role)},
        )
        response = self._create_session_response(membership)
        self.session.commit()
        return response

    def logout(self, token: str | None, context: CurrentUserContext | None = None) -> None:
        if token:
            self.auth.revoke_session(hash_token(token))
        self.audit.create(
            event_type="auth.logout",
            outcome="success",
            workspace_id=context.workspace_id if context else None,
            user_id=context.user_id if context else None,
            resource_type="user",
            resource_id=context.user_id if context else None,
        )
        self.session.commit()

    def me(self, context: CurrentUserContext) -> MeResponse:
        user = self.auth.get_user(context.user_id)
        membership = self.auth.get_membership(context.workspace_id, context.user_id)
        if user is None or membership is None:
            raise ApplicationError(401, "invalid_auth_context", "Authenticated account was not found.")
        return MeResponse(account=_account_response(user, membership))

    def _create_session_response(self, membership: WorkspaceMember) -> AuthSessionResponse:
        user = membership.user or self.auth.get_user(membership.user_id)
        if user is None:
            raise ApplicationError(500, "account_unavailable", "Account is unavailable.")
        token = new_session_token()
        expires_at = datetime.now(UTC) + timedelta(hours=self.settings.auth_session_ttl_hours)
        account_session = self.auth.create_session(
            user_id=membership.user_id,
            workspace_id=membership.workspace_id,
            token_hash=hash_token(token),
            role=_normalize_product_role(membership.role),
            expires_at=expires_at,
        )
        return AuthSessionResponse(
            token=token,
            expires_at=account_session.expires_at,
            account=_account_response(user, membership),
        )


def _normalize_product_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized in {"admin", "owner"}:
        return "Admin"
    return "User"


def _first_membership(user: User) -> WorkspaceMember | None:
    return user.memberships[0] if user.memberships else None


def _account_response(user: User, membership: WorkspaceMember) -> AccountResponse:
    return AccountResponse(
        user_id=user.id,
        workspace_id=membership.workspace_id,
        email=user.email,
        display_name=user.display_name,
        role=_normalize_product_role(membership.role),
    )
