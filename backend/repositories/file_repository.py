from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.models.meeting_models import AccountFile, Meeting


class AccountFileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        workspace_id: str,
        owner_user_id: str,
        object_key: str,
        file_name: str,
        content_type: str,
        size_bytes: int,
        meeting_id: str | None = None,
        asset_id: str | None = None,
    ) -> AccountFile:
        account_file = AccountFile(
            workspace_id=workspace_id,
            owner_user_id=owner_user_id,
            meeting_id=meeting_id,
            asset_id=asset_id,
            object_key=object_key,
            file_name=file_name,
            content_type=content_type,
            size_bytes=size_bytes,
        )
        self.session.add(account_file)
        self.session.flush()
        return account_file

    def get_for_owner(self, *, file_id: str, workspace_id: str, owner_user_id: str) -> AccountFile | None:
        statement = select(AccountFile).where(
            AccountFile.id == file_id,
            AccountFile.workspace_id == workspace_id,
            AccountFile.owner_user_id == owner_user_id,
        )
        return self.session.scalars(statement).first()

    def list_for_owner(self, *, workspace_id: str, owner_user_id: str) -> list[AccountFile]:
        statement = (
            select(AccountFile)
            .where(AccountFile.workspace_id == workspace_id, AccountFile.owner_user_id == owner_user_id)
            .order_by(desc(AccountFile.created_at))
        )
        return list(self.session.scalars(statement).all())

    def list_for_meeting(self, *, workspace_id: str, meeting_id: str) -> list[AccountFile]:
        statement = select(AccountFile).where(
            AccountFile.workspace_id == workspace_id,
            AccountFile.meeting_id == meeting_id,
        )
        return list(self.session.scalars(statement).all())

    def delete(self, account_file: AccountFile) -> None:
        self.session.delete(account_file)
        self.session.flush()

    def linked_meeting_exists(self, account_file: AccountFile) -> bool:
        if account_file.meeting_id is None:
            return False
        return self.session.get(Meeting, account_file.meeting_id) is not None
