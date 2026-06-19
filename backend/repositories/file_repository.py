from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.models.meeting_models import MeetingAsset


class AccountFileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        owner_user_id: str,
        object_key: str,
        file_name: str,
        content_type: str,
        size_bytes: int,
        meeting_id: str | None = None,
    ) -> MeetingAsset:
        account_file = MeetingAsset(
            owner_user_id=owner_user_id,
            meeting_id=meeting_id,
            object_key=object_key,
            file_name=file_name,
            content_type=content_type,
            size_bytes=size_bytes,
            idempotency_key=None,
        )
        self.session.add(account_file)
        self.session.flush()
        return account_file

    def get_for_owner(self, *, file_id: str, owner_user_id: str) -> MeetingAsset | None:
        statement = select(MeetingAsset).where(
            MeetingAsset.id == file_id,
            MeetingAsset.owner_user_id == owner_user_id,
        )
        return self.session.scalars(statement).first()

    def list_for_owner(self, *, owner_user_id: str) -> list[MeetingAsset]:
        statement = (
            select(MeetingAsset)
            .where(MeetingAsset.owner_user_id == owner_user_id)
            .order_by(desc(MeetingAsset.created_at))
        )
        return list(self.session.scalars(statement).all())

    def list_for_user(self, *, owner_user_id: str) -> list[MeetingAsset]:
        return self.list_for_owner(owner_user_id=owner_user_id)

    def delete(self, account_file: MeetingAsset) -> None:
        self.session.delete(account_file)
        self.session.flush()

    def linked_meeting_exists(self, account_file: MeetingAsset) -> bool:
        return account_file.meeting_id is not None
