"""Reset local intelligence artifacts and queue every meeting for v2 processing."""

import argparse

from sqlalchemy import delete, select

from backend.configs.database import SessionLocal
from backend.models.enums import MeetingStatus
from backend.models.meeting_models import ChatMessage, Meeting, MeetingAsset, MeetingChunkRecord, MeetingIntelligenceResult
from backend.providers.vector_provider import get_vector_provider
from backend.tasks.processing_tasks import process_meeting


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as session:
        meetings = list(session.scalars(select(Meeting).order_by(Meeting.created_at.asc())).all())
        asset_meeting_ids = {
            meeting_id
            for meeting_id in session.scalars(select(MeetingAsset.meeting_id)).all()
            if meeting_id
        }
        processable_meetings = [meeting for meeting in meetings if meeting.id in asset_meeting_ids]
        ids = [meeting.id for meeting in processable_meetings]
        if args.dry_run:
            print(f"would_reprocess={len(ids)} meeting_ids={ids}")
            return
        vector_provider = get_vector_provider()
        for meeting_id in ids:
            vector_provider.delete_meeting(meeting_id=meeting_id)
        session.execute(delete(ChatMessage).where(ChatMessage.meeting_id.in_(ids))) if ids else None
        session.execute(delete(MeetingChunkRecord).where(MeetingChunkRecord.meeting_id.in_(ids))) if ids else None
        session.execute(delete(MeetingIntelligenceResult).where(MeetingIntelligenceResult.meeting_id.in_(ids))) if ids else None
        for meeting in processable_meetings:
            meeting.status = MeetingStatus.QUEUED
            meeting.failure_reason = None
            meeting.pending_chat_status = None
        session.commit()
    for meeting_id in ids:
        process_meeting.delay(meeting_id)
    print(f"queued_v2_reprocessing={len(ids)}")


if __name__ == "__main__":
    main()
