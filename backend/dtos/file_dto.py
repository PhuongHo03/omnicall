from datetime import datetime

from pydantic import BaseModel


class AccountFileResponse(BaseModel):
    id: str
    workspace_id: str
    owner_user_id: str
    meeting_id: str | None
    asset_id: str | None
    file_name: str
    content_type: str
    size_bytes: int
    linked_to_meeting: bool
    created_at: datetime


class AccountFileListResponse(BaseModel):
    items: list[AccountFileResponse]


class DeleteResponse(BaseModel):
    id: str
    deleted: bool
