from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from backend.models.enums import MeetingStatus, ProcessingJobStatus
from backend.models.meeting_models import Meeting, MeetingAsset, MeetingIntelligenceResult, ProcessingJob


class MeetingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, user_id: str, title: str, language: str | None) -> Meeting:
        meeting = Meeting(
            owner_user_id=user_id,
            title=title,
            language=language,
            status=MeetingStatus.DRAFT,
        )
        self.session.add(meeting)
        self.session.flush()
        return meeting

    def list_for_owner(self, user_id: str, limit: int = 50, offset: int = 0) -> list[Meeting]:
        statement = (
            select(Meeting)
            .where(Meeting.owner_user_id == user_id)
            .order_by(desc(Meeting.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(statement).all())

    def get(self, meeting_id: str) -> Meeting | None:
        statement = (
            select(Meeting)
            .options(selectinload(Meeting.assets), selectinload(Meeting.processing_jobs))
            .where(Meeting.id == meeting_id)
        )
        return self.session.scalars(statement).first()

    def get_for_owner(self, meeting_id: str, user_id: str) -> Meeting | None:
        statement = (
            select(Meeting)
            .options(selectinload(Meeting.assets), selectinload(Meeting.processing_jobs))
            .where(Meeting.id == meeting_id, Meeting.owner_user_id == user_id)
        )
        return self.session.scalars(statement).first()

    def update_status(
        self,
        meeting: Meeting,
        status: MeetingStatus,
        failure_reason: str | None = None,
    ) -> Meeting:
        meeting.status = status
        meeting.failure_reason = failure_reason
        self.session.flush()
        return meeting


class MeetingAssetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_idempotency_key(self, meeting_id: str, idempotency_key: str) -> MeetingAsset | None:
        statement = select(MeetingAsset).where(
            MeetingAsset.meeting_id == meeting_id,
            MeetingAsset.idempotency_key == idempotency_key,
        )
        return self.session.scalars(statement).first()

    def get_latest_for_meeting(self, meeting_id: str) -> MeetingAsset | None:
        statement = (
            select(MeetingAsset)
            .where(MeetingAsset.meeting_id == meeting_id)
            .order_by(desc(MeetingAsset.created_at))
            .limit(1)
        )
        return self.session.scalars(statement).first()

    def get_for_meeting(self, meeting_id: str, asset_id: str) -> MeetingAsset | None:
        statement = select(MeetingAsset).where(
            MeetingAsset.meeting_id == meeting_id,
            MeetingAsset.id == asset_id,
        )
        return self.session.scalars(statement).first()

    def create(
        self,
        *,
        meeting_id: str,
        user_id: str,
        object_key: str,
        file_name: str,
        content_type: str,
        size_bytes: int,
        idempotency_key: str,
    ) -> MeetingAsset:
        asset = MeetingAsset(
            owner_user_id=user_id,
            meeting_id=meeting_id,
            object_key=object_key,
            file_name=file_name,
            content_type=content_type,
            size_bytes=size_bytes,
            idempotency_key=idempotency_key,
        )
        self.session.add(asset)
        self.session.flush()
        return asset


class ProcessingJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, job_id: str) -> ProcessingJob | None:
        return self.session.get(ProcessingJob, job_id)

    def get_by_idempotency_key(self, meeting_id: str, idempotency_key: str) -> ProcessingJob | None:
        statement = select(ProcessingJob).where(
            ProcessingJob.meeting_id == meeting_id,
            ProcessingJob.idempotency_key == idempotency_key,
        )
        return self.session.scalars(statement).first()

    def get_latest_for_meeting(self, meeting_id: str) -> ProcessingJob | None:
        statement = (
            select(ProcessingJob)
            .where(ProcessingJob.meeting_id == meeting_id)
            .order_by(desc(ProcessingJob.created_at))
            .limit(1)
        )
        return self.session.scalars(statement).first()

    def list_stale_pending(self, *, updated_before: datetime, limit: int) -> list[ProcessingJob]:
        statement = (
            select(ProcessingJob)
            .join(Meeting, Meeting.id == ProcessingJob.meeting_id)
            .where(
                ProcessingJob.status == ProcessingJobStatus.PENDING,
                ProcessingJob.updated_at <= updated_before,
                Meeting.status == MeetingStatus.QUEUED,
            )
            .order_by(ProcessingJob.updated_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(self.session.scalars(statement).all())

    def create(
        self,
        *,
        meeting_id: str,
        idempotency_key: str,
        payload: dict,
        status: ProcessingJobStatus = ProcessingJobStatus.PENDING,
    ) -> ProcessingJob:
        job = ProcessingJob(
            meeting_id=meeting_id,
            idempotency_key=idempotency_key,
            payload=payload,
            status=status,
        )
        self.session.add(job)
        self.session.flush()
        return job

    def update_status(
        self,
        job: ProcessingJob,
        status: ProcessingJobStatus,
        *,
        safe_failure_reason: str | None = None,
        internal_error: str | None = None,
        increment_attempts: bool = False,
    ) -> ProcessingJob:
        job.status = status
        job.safe_failure_reason = safe_failure_reason
        job.internal_error = internal_error
        if increment_attempts:
            job.attempts += 1
        self.session.flush()
        return job

    def mark_failed(self, job: ProcessingJob, safe_failure_reason: str, internal_error: str) -> ProcessingJob:
        job.status = ProcessingJobStatus.FAILED
        job.safe_failure_reason = safe_failure_reason
        job.internal_error = internal_error
        self.session.flush()
        return job


class MeetingIntelligenceResultRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_latest_for_meeting(self, meeting_id: str) -> MeetingIntelligenceResult | None:
        statement = (
            select(MeetingIntelligenceResult)
            .where(MeetingIntelligenceResult.meeting_id == meeting_id)
            .order_by(desc(MeetingIntelligenceResult.created_at))
            .limit(1)
        )
        return self.session.scalars(statement).first()

    def get_by_schema_version(self, meeting_id: str, schema_version: str) -> MeetingIntelligenceResult | None:
        statement = select(MeetingIntelligenceResult).where(
            MeetingIntelligenceResult.meeting_id == meeting_id,
            MeetingIntelligenceResult.schema_version == schema_version,
        )
        return self.session.scalars(statement).first()

    def upsert(
        self,
        *,
        meeting_id: str,
        processing_job_id: str,
        schema_version: str,
        provider_name: str,
        provider_model: str,
        result_json: dict,
    ) -> MeetingIntelligenceResult:
        existing = self.get_by_schema_version(meeting_id, schema_version)
        if existing is not None:
            existing.processing_job_id = processing_job_id
            existing.provider_name = provider_name
            existing.provider_model = provider_model
            existing.result_json = result_json
            self.session.flush()
            return existing

        result = MeetingIntelligenceResult(
            meeting_id=meeting_id,
            processing_job_id=processing_job_id,
            schema_version=schema_version,
            provider_name=provider_name,
            provider_model=provider_model,
            result_json=result_json,
        )
        self.session.add(result)
        self.session.flush()
        return result
