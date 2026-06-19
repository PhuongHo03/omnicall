from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from backend.configs.settings import Settings, get_settings
from backend.dependencies.auth import CurrentUserContext
from backend.dtos.file_dto import AccountFileListResponse, AccountFileResponse, DeleteResponse
from backend.providers.storage_provider import ObjectStorageProvider
from backend.repositories.auth_repository import AuditEventRepository
from backend.repositories.file_repository import AccountFileRepository
from backend.utils.exceptions import ApplicationError


@dataclass(frozen=True)
class AccountFileContent:
    data: bytes
    file_name: str
    content_type: str


class AccountFileService:
    def __init__(
        self,
        session: Session,
        storage_provider: ObjectStorageProvider,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.storage_provider = storage_provider
        self.settings = settings or get_settings()
        self.files = AccountFileRepository(session)
        self.audit = AuditEventRepository(session)

    def list_files(self, context: CurrentUserContext) -> AccountFileListResponse:
        items = self.files.list_for_owner(owner_user_id=context.user_id)
        return AccountFileListResponse(items=[self._file_response(item) for item in items])

    def upload_file(self, context: CurrentUserContext, upload: UploadFile) -> AccountFileResponse:
        file_name = Path(upload.filename or "account-file").name
        content_type = upload.content_type or "application/octet-stream"
        extension = Path(file_name).suffix.lower()
        size_bytes = self._get_upload_size(upload)
        self._validate_upload(extension=extension, content_type=content_type, size_bytes=size_bytes)

        object_key = f"users/{context.user_id}/files/{uuid4()}{extension}"
        upload.file.seek(0)
        self.storage_provider.put_object(
            object_key=object_key,
            data=upload.file,
            size_bytes=size_bytes,
            content_type=content_type,
        )
        account_file = self.files.create(
            owner_user_id=context.user_id,
            object_key=object_key,
            file_name=file_name,
            content_type=content_type,
            size_bytes=size_bytes,
        )
        self.audit.create(
            event_type="file.upload",
            outcome="success",
            user_id=context.user_id,
            resource_type="account_file",
            resource_id=account_file.id,
            metadata={"linkedToMeeting": False, "sizeBytes": size_bytes},
        )
        self.session.commit()
        self.session.refresh(account_file)
        return self._file_response(account_file)

    def get_content(self, context: CurrentUserContext, file_id: str) -> AccountFileContent:
        account_file = self._get_owned_file(context, file_id)
        self.audit.create(
            event_type="file.playback",
            outcome="success",
            user_id=context.user_id,
            resource_type="account_file",
            resource_id=account_file.id,
        )
        self.session.commit()
        return AccountFileContent(
            data=self.storage_provider.get_object_bytes(object_key=account_file.object_key),
            file_name=account_file.file_name,
            content_type=account_file.content_type,
        )

    def delete_file(self, context: CurrentUserContext, file_id: str) -> DeleteResponse:
        account_file = self._get_owned_file(context, file_id)
        if self.files.linked_meeting_exists(account_file):
            self.audit.create(
                event_type="file.delete",
                outcome="blocked",
                user_id=context.user_id,
                resource_type="account_file",
                resource_id=account_file.id,
                metadata={"reason": "linked_meeting_exists", "meetingId": account_file.meeting_id},
            )
            self.session.commit()
            raise ApplicationError(
                409,
                "file_linked_to_meeting",
                "This file is linked to an existing meeting session. Delete the meeting session first.",
            )
        object_key = account_file.object_key
        response = DeleteResponse(id=account_file.id, deleted=True)
        self.files.delete(account_file)
        self.storage_provider.remove_object(object_key=object_key)
        self.audit.create(
            event_type="file.delete",
            outcome="success",
            user_id=context.user_id,
            resource_type="account_file",
            resource_id=response.id,
        )
        self.session.commit()
        return response

    def _get_owned_file(self, context: CurrentUserContext, file_id: str):
        account_file = self.files.get_for_owner(
            file_id=file_id,
            owner_user_id=context.user_id,
        )
        if account_file is None:
            raise ApplicationError(404, "file_not_found", "File was not found.")
        return account_file

    def _validate_upload(self, *, extension: str, content_type: str, size_bytes: int) -> None:
        if extension not in self.settings.upload_allowed_extensions:
            raise ApplicationError(400, "unsupported_file_extension", "This file extension is not supported.")
        if content_type not in self.settings.upload_allowed_content_types:
            raise ApplicationError(400, "unsupported_content_type", "This file content type is not supported.")
        if size_bytes <= 0:
            raise ApplicationError(400, "empty_upload", "Uploaded file is empty.")
        if size_bytes > self.settings.upload_max_bytes:
            raise ApplicationError(413, "upload_too_large", "Uploaded file is too large.")

    @staticmethod
    def _get_upload_size(upload: UploadFile) -> int:
        current_position = upload.file.tell()
        upload.file.seek(0, 2)
        size_bytes = upload.file.tell()
        upload.file.seek(current_position)
        return size_bytes

    def _file_response(self, account_file) -> AccountFileResponse:
        return AccountFileResponse(
            id=account_file.id,
            owner_user_id=account_file.owner_user_id,
            meeting_id=account_file.meeting_id,
            file_name=account_file.file_name,
            content_type=account_file.content_type,
            size_bytes=account_file.size_bytes,
            linked_to_meeting=self.files.linked_meeting_exists(account_file),
            created_at=account_file.created_at,
        )
