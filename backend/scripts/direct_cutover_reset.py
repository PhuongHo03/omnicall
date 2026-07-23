"""Safely reset derived state for the two approved meetings and reprocess audio.

Dry-run is the default. Execution requires both ``--execute`` and a directory
containing a non-empty ``postgres.dump`` created and restore-tested beforehand.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import delete, select

from backend.configs.database import SessionLocal
from backend.models.enums import MeetingStatus
from backend.models.meeting_models import (
    ChatMessage,
    Meeting,
    MeetingAsset,
    MeetingChunkRecord,
    MeetingIntelligenceResult,
    MeetingRetrievalSnapshot,
    MeetingTranscriptWindow,
)
from backend.providers.redis_provider import get_redis_client
from backend.providers.vector_provider import get_vector_provider
from backend.tasks.processing_tasks import process_meeting


APPROVED_MEETING_IDS = (
    "a0cbcd94-0cc1-470d-8093-d501eb382a14",
    "0106313e-d901-4ccf-aae7-40ac47e6a911",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--backup-dir", type=Path, required=True)
    args = parser.parse_args()
    dump = args.backup_dir / "postgres.dump"
    if not dump.is_file() or dump.stat().st_size == 0:
        raise SystemExit("backup_required: backup-dir must contain non-empty postgres.dump")

    with SessionLocal() as session:
        meetings = list(session.scalars(select(Meeting).where(Meeting.id.in_(APPROVED_MEETING_IDS))).all())
        if {meeting.id for meeting in meetings} != set(APPROVED_MEETING_IDS):
            raise SystemExit("approved_meeting_missing")
        assets = list(session.scalars(select(MeetingAsset).where(MeetingAsset.meeting_id.in_(APPROVED_MEETING_IDS))).all())
        if {asset.meeting_id for asset in assets} != set(APPROVED_MEETING_IDS):
            raise SystemExit("source_asset_missing")
        print(f"meetings={len(meetings)} source_assets={len(assets)} execute={args.execute}")
        if not args.execute:
            return

        vectors = get_vector_provider()
        for meeting_id in APPROVED_MEETING_IDS:
            vectors.delete_meeting(meeting_id=meeting_id)
        # Chat feedback and turns cascade from chat_messages.
        session.execute(delete(ChatMessage).where(ChatMessage.meeting_id.in_(APPROVED_MEETING_IDS)))
        session.execute(delete(MeetingChunkRecord).where(MeetingChunkRecord.meeting_id.in_(APPROVED_MEETING_IDS)))
        session.execute(delete(MeetingTranscriptWindow).where(MeetingTranscriptWindow.meeting_id.in_(APPROVED_MEETING_IDS)))
        session.execute(delete(MeetingRetrievalSnapshot).where(MeetingRetrievalSnapshot.meeting_id.in_(APPROVED_MEETING_IDS)))
        session.execute(delete(MeetingIntelligenceResult).where(MeetingIntelligenceResult.meeting_id.in_(APPROVED_MEETING_IDS)))
        for meeting in meetings:
            meeting.status = MeetingStatus.QUEUED
            meeting.failure_reason = None
            meeting.pending_chat_status = None
        session.commit()

    redis = get_redis_client()
    for meeting_id in APPROVED_MEETING_IDS:
        keys = set()
        for pattern in (f"*{meeting_id}*", f"chat:{meeting_id}"):
            keys.update(str(key) for key in redis.scan_iter(match=pattern, count=200))
        if keys:
            redis.delete(*sorted(keys))
        process_meeting.delay(meeting_id)
    print(f"queued_reprocessing={len(APPROVED_MEETING_IDS)}")


if __name__ == "__main__":
    main()
