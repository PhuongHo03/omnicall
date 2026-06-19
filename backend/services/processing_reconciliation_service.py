from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.configs.settings import Settings, get_settings
from backend.providers.lock_provider import RedisLockProvider, get_redis_lock_provider
from backend.providers.queue_provider import ProcessingQueueProvider, get_processing_queue_provider
from backend.repositories.meeting_repository import ProcessingJobRepository


class ProcessingReconciliationService:
    lock_key = "lock:processing-job-reconciliation"

    def __init__(
        self,
        *,
        session: Session,
        settings: Settings | None = None,
        lock_provider: RedisLockProvider | None = None,
        queue_provider: ProcessingQueueProvider | None = None,
        jobs: ProcessingJobRepository | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.lock_provider = lock_provider or get_redis_lock_provider()
        self.queue_provider = queue_provider or get_processing_queue_provider()
        self.jobs = jobs or ProcessingJobRepository(session)

    def reconcile(self) -> dict[str, int | str]:
        lock_ttl = max(self.settings.processing_reconciliation_interval_seconds * 2, 60)
        lock_token = self.lock_provider.acquire(self.lock_key, ttl_seconds=lock_ttl)
        if lock_token is None:
            return {"status": "locked", "scanned": 0, "republished": 0, "failed": 0}

        try:
            now = datetime.now(UTC)
            stale_before = now - timedelta(seconds=self.settings.processing_reconciliation_stale_seconds)
            stale_jobs = self.jobs.list_stale_pending(
                updated_before=stale_before,
                limit=self.settings.processing_reconciliation_batch_size,
            )
            republished = 0
            failed = 0

            for job in stale_jobs:
                try:
                    self.queue_provider.enqueue_meeting_processing(
                        job_id=job.id,
                        meeting_id=job.meeting_id,
                    )
                except Exception:
                    failed += 1
                    continue

                previous = job.payload.get("reconciliation", {}) if isinstance(job.payload, dict) else {}
                job.payload = {
                    **(job.payload if isinstance(job.payload, dict) else {}),
                    "reconciliation": {
                        "republishCount": int(previous.get("republishCount", 0)) + 1,
                        "lastRepublishedAt": now.isoformat(),
                    },
                }
                republished += 1

            self.session.commit()
            return {
                "status": "completed",
                "scanned": len(stale_jobs),
                "republished": republished,
                "failed": failed,
            }
        finally:
            self.lock_provider.release(self.lock_key, lock_token)
