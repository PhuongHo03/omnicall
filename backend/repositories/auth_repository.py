from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.core_models import User, Workspace, WorkspaceMember


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_user(self, user_id: str) -> User | None:
        return self.session.get(User, user_id)

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
            membership = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="owner")
            self.session.add(membership)

        self.session.flush()
        return membership
