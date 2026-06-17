from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from backend.configs.settings import Settings, get_settings
from backend.dependencies.auth import CurrentUserContext
from backend.dtos.meeting_dto import (
    MeetingAssetResponse,
    MeetingCreateRequest,
    MeetingResponse,
    ProcessingJobResponse,
    ProcessingStatusResponse,
)
from backend.models.enums import MeetingStatus, ProcessingJobStatus
from backend.models.meeting_models import Meeting, MeetingAsset, ProcessingJob
from backend.providers.queue_provider import ProcessingQueueProvider
from backend.providers.storage_provider import ObjectStorageProvider
from backend.repositories.auth_repository import AuditEventRepository
from backend.repositories.file_repository import AccountFileRepository
from backend.repositories.meeting_repository import (
    MeetingAssetRepository,
    MeetingRepository,
    ProcessingJobRepository,
)
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
    ) -> None:
        self.session = session
        self.meetings = MeetingRepository(session)
        self.assets = MeetingAssetRepository(session)
        self.jobs = ProcessingJobRepository(session)
        self.account_files = AccountFileRepository(session)
        self.audit = AuditEventRepository(session)
        self.storage_provider = storage_provider
        self.queue_provider = queue_provider
        self.settings = settings

    def create_meeting(self, context: CurrentUserContext, request: MeetingCreateRequest) -> MeetingResponse:
        meeting = self.meetings.create(
            workspace_id=context.workspace_id,
            user_id=context.user_id,
            title=request.title.strip(),
            language=request.language,
        )
        self.session.commit()
        self.session.refresh(meeting)
        return self._meeting_response(meeting)

    def list_meetings(self, context: CurrentUserContext, limit: int, offset: int) -> list[MeetingResponse]:
        meetings = self.meetings.list_for_workspace(context.workspace_id, limit=limit, offset=offset)
        return [self._meeting_response(meeting) for meeting in meetings]

    def get_meeting(self, context: CurrentUserContext, meeting_id: str) -> MeetingResponse:
        meeting = self._get_authorized_meeting(context, meeting_id)
        return self._meeting_response(meeting)

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

        if meeting.status in {MeetingStatus.QUEUED, MeetingStatus.PROCESSING, MeetingStatus.READY, MeetingStatus.FAILED}:
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
            f"workspaces/{context.workspace_id}/meetings/{meeting.id}"
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
            workspace_id=context.workspace_id,
            meeting_id=meeting.id,
            user_id=context.user_id,
            object_key=object_key,
            file_name=file_name,
            content_type=content_type,
            size_bytes=size_bytes,
            idempotency_key=idempotency_key,
        )
        self.account_files.create(
            workspace_id=context.workspace_id,
            owner_user_id=context.user_id,
            meeting_id=meeting.id,
            asset_id=asset.id,
            object_key=object_key,
            file_name=file_name,
            content_type=content_type,
            size_bytes=size_bytes,
        )
        self.meetings.update_status(meeting, MeetingStatus.UPLOADED)
        self.audit.create(
            event_type="meeting.upload",
            outcome="success",
            workspace_id=context.workspace_id,
            user_id=context.user_id,
            resource_type="meeting",
            resource_id=meeting.id,
            metadata={"assetId": asset.id, "sizeBytes": size_bytes},
        )
        self.session.commit()
        self.session.refresh(asset)
        return self._asset_response(asset)

    def queue_processing(
        self,
        context: CurrentUserContext,
        meeting_id: str,
        idempotency_key: str,
    ) -> ProcessingJobResponse:
        meeting = self._get_authorized_meeting(context, meeting_id)

        existing = self.jobs.get_by_idempotency_key(meeting.id, idempotency_key)
        if existing is not None:
            return self._job_response(existing)

        if meeting.status in {MeetingStatus.QUEUED, MeetingStatus.PROCESSING, MeetingStatus.READY}:
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

        job = self.jobs.create(
            workspace_id=context.workspace_id,
            meeting_id=meeting.id,
            idempotency_key=idempotency_key,
            payload={"meetingId": meeting.id},
        )
        self.meetings.update_status(meeting, MeetingStatus.QUEUED)
        self.session.commit()
        self.session.refresh(job)

        try:
            self.queue_provider.enqueue_meeting_processing(job_id=job.id, meeting_id=meeting.id)
        except Exception as exc:
            safe_reason = "Processing queue is unavailable. Please retry later."
            self.jobs.mark_failed(job, safe_reason, repr(exc))
            self.meetings.update_status(meeting, MeetingStatus.FAILED, safe_reason)
            self.session.commit()
            self.session.refresh(job)

        return self._job_response(job)

    def get_processing_status(self, context: CurrentUserContext, meeting_id: str) -> ProcessingStatusResponse:
        meeting = self._get_authorized_meeting(context, meeting_id)
        latest_job = self.jobs.get_latest_for_meeting(meeting.id)
        latest_asset = self.assets.get_latest_for_meeting(meeting.id)
        return ProcessingStatusResponse(
            meeting=self._meeting_response(meeting),
            latest_job=self._job_response(latest_job) if latest_job else None,
            latest_asset=self._asset_response(latest_asset) if latest_asset else None,
        )

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
        meeting = self.meetings.get_for_workspace(meeting_id, context.workspace_id)
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

    @staticmethod
    def _get_upload_size(upload: UploadFile) -> int:
        current_position = upload.file.tell()
        upload.file.seek(0, 2)
        size_bytes = upload.file.tell()
        upload.file.seek(current_position)
        return size_bytes

    @staticmethod
    def _meeting_response(meeting: Meeting) -> MeetingResponse:
        return MeetingResponse(
            id=meeting.id,
            workspace_id=meeting.workspace_id,
            title=meeting.title,
            language=meeting.language,
            status=meeting.status,
            failure_reason=meeting.failure_reason,
            created_at=meeting.created_at,
            updated_at=meeting.updated_at,
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

    @staticmethod
    def _job_response(job: ProcessingJob) -> ProcessingJobResponse:
        return ProcessingJobResponse(
            id=job.id,
            meeting_id=job.meeting_id,
            status=job.status,
            safe_failure_reason=job.safe_failure_reason,
            retry_allowed=job.status in {ProcessingJobStatus.FAILED, ProcessingJobStatus.CANCELLED},
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


def get_meeting_service(
    session: Session,
    storage_provider: ObjectStorageProvider,
    queue_provider: ProcessingQueueProvider,
) -> MeetingService:
    return MeetingService(session, storage_provider, queue_provider, get_settings())
