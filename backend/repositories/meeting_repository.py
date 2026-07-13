from datetime import datetime
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.models.enums import MeetingStatus
from backend.models.meeting_models import Meeting, MeetingAsset, MeetingIntelligenceResult


class MeetingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, user_id: str, title: str | None = None) -> Meeting:
        meeting_id = str(uuid4())
        meeting = Meeting(
            id=meeting_id,
            owner_user_id=user_id,
            title=title.strip() if title and title.strip() else meeting_id,
            status=MeetingStatus.DRAFT,
        )
        self.session.add(meeting)
        self.session.flush()
        return meeting

    def update_title(self, meeting: Meeting, title: str) -> Meeting:
        meeting.title = title.strip()
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
        return self.session.get(Meeting, meeting_id)

    def get_for_owner(self, meeting_id: str, owner_user_id: str) -> Meeting | None:
        statement = select(Meeting).where(Meeting.id == meeting_id, Meeting.owner_user_id == owner_user_id)
        return self.session.scalars(statement).first()

    def update_status(self, meeting: Meeting, status: MeetingStatus, failure_reason: str | None = None) -> Meeting:
        meeting.status = status
        if status != MeetingStatus.FAILED:
            meeting.failure_reason = None
        elif failure_reason is not None:
            meeting.failure_reason = failure_reason
        self.session.flush()
        return meeting

    def increment_attempts(self, meeting: Meeting) -> Meeting:
        meeting.attempts = (meeting.attempts or 0) + 1
        self.session.flush()
        return meeting

    def list_stale_queued(self, *, updated_before: datetime, limit: int) -> list[Meeting]:
        statement = (
            select(Meeting)
            .where(
                Meeting.status == MeetingStatus.QUEUED,
                Meeting.updated_at <= updated_before,
            )
            .order_by(Meeting.updated_at)
            .limit(limit)
        )
        return list(self.session.scalars(statement).all())


class MeetingAssetRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

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
            meeting_id=meeting_id,
            owner_user_id=user_id,
            object_key=object_key,
            file_name=file_name,
            content_type=content_type,
            size_bytes=size_bytes,
            idempotency_key=idempotency_key,
        )
        self.session.add(asset)
        self.session.flush()
        return asset

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

    def get_by_idempotency_key(self, meeting_id: str, idempotency_key: str) -> MeetingAsset | None:
        statement = select(MeetingAsset).where(
            MeetingAsset.meeting_id == meeting_id,
            MeetingAsset.idempotency_key == idempotency_key,
        )
        return self.session.scalars(statement).first()


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

    def upsert(
        self,
        *,
        meeting_id: str,
        schema_version: str,
        provider_name: str,
        provider_model: str,
        result_json: dict,
    ) -> MeetingIntelligenceResult:
        existing = self.get_latest_for_meeting(meeting_id)
        if existing and existing.schema_version == schema_version:
            existing.provider_name = provider_name
            existing.provider_model = provider_model
            existing.result_json = result_json
            self.session.flush()
            return existing
        result = MeetingIntelligenceResult(
            meeting_id=meeting_id,
            schema_version=schema_version,
            provider_name=provider_name,
            provider_model=provider_model,
            result_json=result_json,
        )
        self.session.add(result)
        self.session.flush()
        return result
