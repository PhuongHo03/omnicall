from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.models.meeting_models import MeetingTranscriptWindow


class TranscriptWindowRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_for_generation(
        self,
        *,
        meeting_id: str,
        generation: str,
        windows: list[dict],
        intelligence_result_id: str | None = None,
    ) -> list[MeetingTranscriptWindow]:
        self.session.execute(
            delete(MeetingTranscriptWindow).where(
                MeetingTranscriptWindow.meeting_id == meeting_id,
                MeetingTranscriptWindow.generation == generation,
            )
        )
        records: list[MeetingTranscriptWindow] = []
        now = datetime.now(UTC)
        for window in windows:
            record = MeetingTranscriptWindow(
                id=str(uuid4()),
                meeting_id=meeting_id,
                intelligence_result_id=intelligence_result_id,
                generation=generation,
                window_id=window["windowId"],
                sequence_no=window["sequenceNo"],
                start_ms=window.get("startMs"),
                end_ms=window.get("endMs"),
                segment_ids=window.get("segmentIds", []),
                token_count=window.get("tokenCount", 0),
                window_hash=window["windowHash"],
                status="pending",
                created_at=now,
                updated_at=now,
            )
            self.session.add(record)
            records.append(record)
        self.session.flush()
        return records

    def list_for_generation(self, *, meeting_id: str, generation: str) -> list[MeetingTranscriptWindow]:
        statement = (
            select(MeetingTranscriptWindow)
            .where(
                MeetingTranscriptWindow.meeting_id == meeting_id,
                MeetingTranscriptWindow.generation == generation,
            )
            .order_by(MeetingTranscriptWindow.sequence_no)
        )
        return list(self.session.scalars(statement).all())

    def get(self, *, meeting_id: str, generation: str, window_id: str) -> MeetingTranscriptWindow | None:
        statement = select(MeetingTranscriptWindow).where(
            MeetingTranscriptWindow.meeting_id == meeting_id,
            MeetingTranscriptWindow.generation == generation,
            MeetingTranscriptWindow.window_id == window_id,
        )
        return self.session.scalars(statement).first()

    def mark_processing(self, window: MeetingTranscriptWindow) -> None:
        window.status = "processing"
        window.attempt_count = (window.attempt_count or 0) + 1
        window.started_at = datetime.now(UTC)
        window.error_message = None
        self.session.flush()

    def mark_succeeded(self, window: MeetingTranscriptWindow, local_result: dict) -> None:
        window.status = "succeeded"
        window.local_result_json = local_result
        window.completed_at = datetime.now(UTC)
        window.updated_at = datetime.now(UTC)
        window.error_message = None
        self.session.flush()

    def mark_failed(self, window: MeetingTranscriptWindow, error: str) -> None:
        window.status = "failed"
        window.error_message = error[:4000]
        window.updated_at = datetime.now(UTC)
        self.session.flush()

    def attach_result(self, *, meeting_id: str, generation: str, result_id: str) -> None:
        records = self.list_for_generation(meeting_id=meeting_id, generation=generation)
        for record in records:
            record.intelligence_result_id = result_id
        self.session.flush()
