from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.configs.settings import Settings, get_settings
from backend.dependencies.auth import CurrentUserContext
from backend.dtos.meeting_dto import (
    MeetingAssetResponse,
    MeetingCreateRequest,
    MeetingDetailResponse,
    MeetingResponse,
)
from backend.models.enums import MeetingStatus
from backend.models.meeting_models import Meeting, MeetingAsset
from backend.providers.queue_provider import ProcessingQueueProvider
from backend.providers.storage_provider import ObjectStorageProvider
from backend.repositories.auth_repository import AuditEventRepository
from backend.repositories.meeting_repository import (
    MeetingAssetRepository,
    MeetingRepository,
)
from backend.services.operational_log_service import OperationalLogService
from backend.utils.exceptions import ApplicationError


@dataclass(frozen=True)
class MeetingAssetContent:
    data: bytes
    file_name: str
    content_type: str


class MeetingService:
    def __init__(
        self,
        session: Session,
        storage_provider: ObjectStorageProvider,
        queue_provider: ProcessingQueueProvider,
        settings: Settings,
        operational_logs: OperationalLogService | None = None,
    ) -> None:
        self.session = session
        self.meetings = MeetingRepository(session)
        self.assets = MeetingAssetRepository(session)
        self.audit = AuditEventRepository(session)
        self.storage_provider = storage_provider
        self.queue_provider = queue_provider
        self.settings = settings
        self.operational_logs = operational_logs

    def create_meeting(self, context: CurrentUserContext, request: MeetingCreateRequest) -> MeetingResponse:
        meeting = self.meetings.create(
            user_id=context.user_id,
            title=request.title,
        )
        self.session.commit()
        self.session.refresh(meeting)
        return self._meeting_response(meeting)

    def update_meeting_title(self, context: CurrentUserContext, meeting_id: str, title: str) -> MeetingResponse:
        if not title.strip():
            raise ApplicationError(400, "empty_meeting_title", "Meeting title must not be empty.")
        meeting = self._get_authorized_meeting(context, meeting_id)
        updated = self.meetings.update_title(meeting, title)
        self.session.commit()
        self.session.refresh(updated)
        return self._meeting_response(updated, self.assets.get_latest_for_meeting(updated.id))

    def list_meetings(self, context: CurrentUserContext, limit: int, offset: int) -> list[MeetingResponse]:
        meetings = self.meetings.list_for_owner(context.user_id, limit=limit, offset=offset)
        return [self._meeting_response(m, self.assets.get_latest_for_meeting(m.id)) for m in meetings]

    def get_meeting(self, context: CurrentUserContext, meeting_id: str) -> MeetingDetailResponse:
        meeting = self._get_authorized_meeting(context, meeting_id)
        latest_asset = self.assets.get_latest_for_meeting(meeting.id)
        return self._meeting_detail_response(meeting, latest_asset)

    def upload_asset(
        self,
        context: CurrentUserContext,
        meeting_id: str,
        upload: UploadFile,
        idempotency_key: str,
    ) -> MeetingAssetResponse:
        meeting = self._get_authorized_meeting(context, meeting_id)
        existing = self.assets.get_by_idempotency_key(meeting.id, idempotency_key)
        if existing is not None:
            return self._asset_response(existing)

        if meeting.assets:
            raise ApplicationError(
                409,
                "meeting_already_has_asset",
                "This meeting already has an uploaded file. Create a new meeting for another analysis.",
            )

        if meeting.status in {MeetingStatus.UPLOADED, MeetingStatus.QUEUED, MeetingStatus.PROCESSING, MeetingStatus.READY, MeetingStatus.FAILED}:
            raise ApplicationError(
                409,
                "meeting_not_uploadable",
                "This meeting cannot accept new uploads in its current state.",
            )

        file_name = Path(upload.filename or "meeting-upload").name
        content_type = upload.content_type or "application/octet-stream"
        extension = Path(file_name).suffix.lower()
        size_bytes = self._get_upload_size(upload)

        self._validate_upload(extension=extension, content_type=content_type, size_bytes=size_bytes)

        object_key = (
            f"users/{context.user_id}/meetings/{meeting.id}"
            f"/uploads/{uuid4()}{extension}"
        )

        upload.file.seek(0)
        self.storage_provider.put_object(
            object_key=object_key,
            data=upload.file,
            size_bytes=size_bytes,
            content_type=content_type,
        )

        asset = self.assets.create(
            meeting_id=meeting.id,
            user_id=context.user_id,
            object_key=object_key,
            file_name=file_name,
            content_type=content_type,
            size_bytes=size_bytes,
            idempotency_key=idempotency_key,
        )
        self.audit.create(
            event_type="meeting.upload",
            outcome="success",
            user_id=context.user_id,
            resource_type="meeting",
            resource_id=meeting.id,
            metadata={"assetId": asset.id, "sizeBytes": size_bytes},
        )
        self.meetings.update_status(meeting, MeetingStatus.UPLOADED)
        self.session.commit()
        self.session.refresh(asset)
        self._emit(
            level="info",
            flow="processing",
            stage="file",
            status="succeeded",
            message="Meeting file uploaded.",
            workspace_id=context.user_id,
            meeting_id=meeting.id,
            meeting_name=meeting.title,
            file=_asset_log_context(asset),
            details={"source": "browser_upload"},
        )
        return self._asset_response(asset)

    def queue_processing(
        self,
        context: CurrentUserContext,
        meeting_id: str,
        idempotency_key: str,
    ) -> MeetingDetailResponse:
        meeting = self._get_authorized_meeting(context, meeting_id)

        if meeting.status in {MeetingStatus.QUEUED, MeetingStatus.PROCESSING}:
            raise ApplicationError(
                409,
                "meeting_task_already_pending",
                "This meeting already has a pending processing task. Please wait for it to complete.",
            )

        if meeting.status == MeetingStatus.READY:
            return self._meeting_detail_response(meeting, self.assets.get_latest_for_meeting(meeting.id))

        if meeting.status not in {MeetingStatus.UPLOADED, MeetingStatus.FAILED}:
            raise ApplicationError(
                409,
                "meeting_not_processable",
                "This meeting cannot be queued for processing in its current state.",
            )

        if not meeting.assets:
            raise ApplicationError(
                409,
                "meeting_has_no_asset",
                "Upload a meeting file before starting processing.",
            )

        active_task_count = self.session.scalar(
            select(func.count()).select_from(Meeting).where(
                Meeting.owner_user_id == context.user_id,
                Meeting.status.in_({MeetingStatus.QUEUED, MeetingStatus.PROCESSING}),
            )
        )
        if active_task_count >= self.settings.task_limit_per_user:
            raise ApplicationError(
                429,
                "task_limit_exceeded",
                "Too many tasks pending. Please wait for current processing to complete.",
            )

        self.meetings.update_status(meeting, MeetingStatus.QUEUED)
        self.session.commit()

        try:
            self.queue_provider.enqueue_meeting_processing(meeting_id=meeting.id)
            asset = self.assets.get_latest_for_meeting(meeting.id)
            self._emit(
                level="info",
                flow="processing",
                stage="queued",
                status="succeeded",
                message="Meeting processing queued.",
                workspace_id=context.user_id,
                meeting_id=meeting.id,
                meeting_name=meeting.title,
                file=_asset_log_context(asset),
            )
        except Exception as exc:
            safe_reason = "Processing queue is unavailable. Please retry later."
            self.meetings.update_status(meeting, MeetingStatus.FAILED, safe_reason)
            self.session.commit()
            self.session.refresh(meeting)
            asset = self.assets.get_latest_for_meeting(meeting.id)
            self._emit(
                level="error",
                flow="processing",
                stage="queued",
                status="failed",
                message="Meeting processing could not be queued.",
                workspace_id=context.user_id,
                meeting_id=meeting.id,
                meeting_name=meeting.title,
                file=_asset_log_context(asset),
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

        return self._meeting_detail_response(meeting, self.assets.get_latest_for_meeting(meeting.id))


    def get_asset_content(self, context: CurrentUserContext, meeting_id: str, asset_id: str) -> MeetingAssetContent:
        meeting = self._get_authorized_meeting(context, meeting_id)
        asset = self.assets.get_for_meeting(meeting.id, asset_id)
        if asset is None:
            raise ApplicationError(404, "asset_not_found", "Meeting asset was not found.")
        return MeetingAssetContent(
            data=self.storage_provider.get_object_bytes(object_key=asset.object_key),
            file_name=asset.file_name,
            content_type=asset.content_type,
        )

    def _get_authorized_meeting(self, context: CurrentUserContext, meeting_id: str) -> Meeting:
        meeting = self.meetings.get_for_owner(meeting_id, context.user_id)
        if meeting is None:
            raise ApplicationError(404, "meeting_not_found", "Meeting was not found.")
        return meeting

    def _validate_upload(self, *, extension: str, content_type: str, size_bytes: int) -> None:
        if extension not in self.settings.upload_allowed_extensions:
            raise ApplicationError(400, "unsupported_file_extension", "This meeting file extension is not supported.")
        if content_type not in self.settings.upload_allowed_content_types:
            raise ApplicationError(400, "unsupported_content_type", "This meeting file content type is not supported.")
        if size_bytes <= 0:
            raise ApplicationError(400, "empty_upload", "Uploaded meeting file is empty.")
        if size_bytes > self.settings.upload_max_bytes:
            raise ApplicationError(413, "upload_too_large", "Uploaded meeting file is too large.")

    def _emit(self, **event) -> None:
        if self.operational_logs is not None:
            self.operational_logs.emit(**event)

    @staticmethod
    def _get_upload_size(upload: UploadFile) -> int:
        current_position = upload.file.tell()
        upload.file.seek(0, 2)
        size_bytes = upload.file.tell()
        upload.file.seek(current_position)
        return size_bytes

    @staticmethod
    def _meeting_response(meeting: Meeting, latest_asset: MeetingAsset | None = None) -> MeetingResponse:
        return MeetingResponse(
            id=meeting.id,
            title=meeting.title,
            status=meeting.status,
            failure_reason=meeting.failure_reason,
            pending_chat_status=meeting.pending_chat_status,
            created_at=meeting.created_at,
            latest_asset=MeetingService._asset_response(latest_asset) if latest_asset else None,
            updated_at=meeting.updated_at,
        )

    @staticmethod
    def _meeting_detail_response(
        meeting: Meeting,
        latest_asset: MeetingAsset | None,
    ) -> MeetingDetailResponse:
        return MeetingDetailResponse(
            id=meeting.id,
            title=meeting.title,
            status=meeting.status,
            failure_reason=meeting.failure_reason,
            pending_chat_status=meeting.pending_chat_status,
            created_at=meeting.created_at,
            updated_at=meeting.updated_at,
            latest_asset=MeetingService._asset_response(latest_asset) if latest_asset else None,
            retry_allowed=meeting.status == MeetingStatus.FAILED,
        )

    @staticmethod
    def _asset_response(asset: MeetingAsset) -> MeetingAssetResponse:
        return MeetingAssetResponse(
            id=asset.id,
            meeting_id=asset.meeting_id,
            object_key=asset.object_key,
            file_name=asset.file_name,
            content_type=asset.content_type,
            size_bytes=asset.size_bytes,
            created_at=asset.created_at,
        )



def get_meeting_service(
    session: Session,
    storage_provider: ObjectStorageProvider,
    queue_provider: ProcessingQueueProvider,
) -> MeetingService:
    return MeetingService(session, storage_provider, queue_provider, get_settings())


def _asset_log_context(asset: MeetingAsset | None) -> dict:
    if asset is None:
        return {}
    return {
        "id": asset.id,
        "name": asset.file_name,
        "contentType": asset.content_type,
        "sizeBytes": asset.size_bytes,
        "objectKey": asset.object_key,
    }
