from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.core_models import AccountSession, AuditEvent, User, Workspace, WorkspaceMember


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_user(self, user_id: str) -> User | None:
        return self.session.get(User, user_id)

    def get_user_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email.lower())
        return self.session.scalars(statement).first()

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        return self.session.get(Workspace, workspace_id)

    def get_membership(self, workspace_id: str, user_id: str) -> WorkspaceMember | None:
        statement = select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        return self.session.scalars(statement).first()

    def upsert_dev_context(
        self,
        *,
        user_id: str,
        workspace_id: str,
        email: str,
        display_name: str,
        workspace_name: str,
        role: str = "Admin",
    ) -> WorkspaceMember:
        user = self.get_user(user_id)
        if user is None:
            user = User(id=user_id, email=email, display_name=display_name)
            self.session.add(user)

        workspace = self.get_workspace(workspace_id)
        if workspace is None:
            workspace = Workspace(id=workspace_id, name=workspace_name)
            self.session.add(workspace)

        membership = self.get_membership(workspace_id, user_id)
        if membership is None:
            membership = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role)
            self.session.add(membership)
        else:
            membership.role = role

        self.session.flush()
        return membership

    def create_account(
        self,
        *,
        email: str,
        display_name: str,
        password_hash: str,
        role: str,
        workspace_name: str,
    ) -> WorkspaceMember:
        user = User(email=email.lower(), display_name=display_name, password_hash=password_hash)
        workspace = Workspace(name=workspace_name)
        self.session.add_all([user, workspace])
        self.session.flush()
        membership = WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=role)
        self.session.add(membership)
        self.session.flush()
        return membership

    def create_session(
        self,
        *,
        user_id: str,
        workspace_id: str,
        token_hash: str,
        role: str,
        expires_at: datetime,
    ) -> AccountSession:
        session = AccountSession(
            user_id=user_id,
            workspace_id=workspace_id,
            token_hash=token_hash,
            role=role,
            expires_at=expires_at,
        )
        self.session.add(session)
        self.session.flush()
        return session

    def get_active_session_by_token_hash(self, token_hash: str) -> AccountSession | None:
        statement = select(AccountSession).where(AccountSession.token_hash == token_hash)
        account_session = self.session.scalars(statement).first()
        if account_session is None:
            return None
        now = datetime.now(UTC)
        if account_session.revoked_at is not None or account_session.expires_at <= now:
            return None
        return account_session

    def revoke_session(self, token_hash: str) -> AccountSession | None:
        account_session = self.get_active_session_by_token_hash(token_hash)
        if account_session is None:
            return None
        account_session.revoked_at = datetime.now(UTC)
        self.session.flush()
        return account_session


class AuditEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        event_type: str,
        outcome: str,
        workspace_id: str | None = None,
        user_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        metadata: dict | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            workspace_id=workspace_id,
            user_id=user_id,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            metadata_json=metadata or {},
        )
        self.session.add(event)
        self.session.flush()
        return event
