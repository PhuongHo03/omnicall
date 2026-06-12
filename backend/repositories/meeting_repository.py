from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session, selectinload

from backend.models.enums import MeetingStatus, ProcessingJobStatus
from backend.models.meeting_models import (
    Meeting,
    MeetingAsset,
    MeetingInsightRecord,
    MeetingIntelligenceResult,
    ProcessingJob,
    TranscriptSegmentRecord,
)


class MeetingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, workspace_id: str, user_id: str, title: str, language: str | None) -> Meeting:
        meeting = Meeting(
            workspace_id=workspace_id,
            created_by_user_id=user_id,
            title=title,
            language=language,
            status=MeetingStatus.DRAFT,
        )
        self.session.add(meeting)
        self.session.flush()
        return meeting

    def list_for_workspace(self, workspace_id: str, limit: int = 50, offset: int = 0) -> list[Meeting]:
        statement = (
            select(Meeting)
            .where(Meeting.workspace_id == workspace_id)
            .order_by(desc(Meeting.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(statement).all())

    def get_for_workspace(self, meeting_id: str, workspace_id: str) -> Meeting | None:
        statement = (
            select(Meeting)
            .options(selectinload(Meeting.assets), selectinload(Meeting.processing_jobs))
            .where(Meeting.id == meeting_id, Meeting.workspace_id == workspace_id)
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

    def create(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        user_id: str,
        object_key: str,
        file_name: str,
        content_type: str,
        size_bytes: int,
        idempotency_key: str,
    ) -> MeetingAsset:
        asset = MeetingAsset(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            created_by_user_id=user_id,
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

    def create(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        idempotency_key: str,
        payload: dict,
        status: ProcessingJobStatus = ProcessingJobStatus.PENDING,
    ) -> ProcessingJob:
        job = ProcessingJob(
            workspace_id=workspace_id,
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
        workspace_id: str,
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
            workspace_id=workspace_id,
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


class TranscriptSegmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_for_result(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        intelligence_result_id: str,
        segments: list[dict],
    ) -> list[TranscriptSegmentRecord]:
        self.session.execute(delete(TranscriptSegmentRecord).where(TranscriptSegmentRecord.meeting_id == meeting_id))
        records: list[TranscriptSegmentRecord] = []
        for segment in segments:
            record = TranscriptSegmentRecord(
                workspace_id=workspace_id,
                meeting_id=meeting_id,
                intelligence_result_id=intelligence_result_id,
                segment_id=segment["id"],
                speaker=segment.get("speaker"),
                start_ms=int(segment.get("startMs") or 0),
                end_ms=int(segment.get("endMs") or 0),
                text=segment.get("text") or "",
                confidence=segment.get("confidence"),
            )
            self.session.add(record)
            records.append(record)
        self.session.flush()
        return records


class MeetingInsightRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_for_result(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        intelligence_result_id: str,
        insights: list[dict],
    ) -> list[MeetingInsightRecord]:
        self.session.execute(delete(MeetingInsightRecord).where(MeetingInsightRecord.meeting_id == meeting_id))
        records: list[MeetingInsightRecord] = []
        for insight in insights:
            record = MeetingInsightRecord(
                workspace_id=workspace_id,
                meeting_id=meeting_id,
                intelligence_result_id=intelligence_result_id,
                section=insight["section"],
                item_id=insight["itemId"],
                title=insight.get("title"),
                text=insight["text"],
                citation_ids=insight.get("citationIds", []),
                segment_ids=insight.get("segmentIds", []),
                payload=insight.get("payload", {}),
            )
            self.session.add(record)
            records.append(record)
        self.session.flush()
        return records
