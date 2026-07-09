from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.configs.settings import Settings, get_settings
from backend.models.enums import MeetingStatus
from backend.models.meeting_models import Meeting
from backend.providers.lock_provider import RedisLockProvider, get_redis_lock_provider
from backend.providers.queue_provider import ProcessingQueueProvider, get_processing_queue_provider
from backend.repositories.meeting_repository import MeetingRepository


class ProcessingReconciliationService:
    lock_key = "lock:processing-meeting-reconciliation"

    def __init__(
        self,
        *,
        session: Session,
        settings: Settings | None = None,
        lock_provider: RedisLockProvider | None = None,
        queue_provider: ProcessingQueueProvider | None = None,
        meetings: MeetingRepository | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.lock_provider = lock_provider or get_redis_lock_provider()
        self.queue_provider = queue_provider or get_processing_queue_provider()
        self.meetings = meetings or MeetingRepository(session)

    def reconcile(self) -> dict[str, int | str]:
        lock_ttl = max(self.settings.processing_reconciliation_interval_seconds * 2, 60)
        lock_token = self.lock_provider.acquire(self.lock_key, ttl_seconds=lock_ttl)
        if lock_token is None:
            return {"status": "locked", "scanned": 0, "republished": 0, "failed": 0}

        try:
            now = datetime.now(UTC)
            stale_before = now - timedelta(seconds=self.settings.processing_reconciliation_stale_seconds)
            stale_meetings = self.meetings.list_stale_queued(
                updated_before=stale_before,
                limit=self.settings.processing_reconciliation_batch_size,
            )
            republished = 0
            failed = 0

            for meeting in stale_meetings:
                try:
                    self.queue_provider.enqueue_meeting_processing(
                        meeting_id=meeting.id,
                    )
                except Exception:
                    failed += 1
                    continue

                republished += 1

            self.session.commit()
            # Also cleanup stale pending_chat_status
            stale_chat_count = self.cleanup_stale_pending_chat(stale_seconds=60)
            
            return {
                "status": "completed",
                "scanned": len(stale_meetings),
                "republished": republished,
                "failed": failed,
                "stale_chat_cleanup": stale_chat_count,
            }
        finally:
            self.lock_provider.release(self.lock_key, lock_token)

    def cleanup_stale_pending_chat(self, *, stale_seconds: int = 60) -> int:
        """Reset pending_chat_status for meetings stuck in 'started' state."""
        from datetime import UTC, datetime, timedelta
        
        now = datetime.now(UTC)
        stale_before = now - timedelta(seconds=stale_seconds)
        
        # Find meetings with pending_chat_status = 'started' for too long
        stale_meetings = self.session.query(Meeting).filter(
            Meeting.pending_chat_status == "started",
            Meeting.updated_at < stale_before,
        ).all()
        
        count = 0
        for meeting in stale_meetings:
            meeting.pending_chat_status = None
            count += 1
        
        if count > 0:
            self.session.commit()
        
        return count
