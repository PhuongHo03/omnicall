import unittest
from types import SimpleNamespace

from backend.configs.settings import Settings
from backend.services.processing_reconciliation_service import ProcessingReconciliationService


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


class FakeLockProvider:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.acquired: list[tuple[str, int | None]] = []
        self.released: list[tuple[str, str]] = []

    def acquire(self, key: str, ttl_seconds: int | None = None) -> str | None:
        self.acquired.append((key, ttl_seconds))
        return "token" if self.available else None

    def release(self, key: str, token: str) -> None:
        self.released.append((key, token))


class FakeQueueProvider:
    def __init__(self, *, failing_job_id: str | None = None) -> None:
        self.failing_job_id = failing_job_id
        self.enqueued: list[tuple[str, str]] = []

    def enqueue_meeting_processing(self, *, job_id: str, meeting_id: str) -> None:
        if job_id == self.failing_job_id:
            raise RuntimeError("broker unavailable")
        self.enqueued.append((job_id, meeting_id))


class FakeJobRepository:
    def __init__(self, jobs: list[SimpleNamespace]) -> None:
        self.jobs = jobs
        self.updated_before = None
        self.limit = None

    def list_stale_pending(self, *, updated_before, limit: int):
        self.updated_before = updated_before
        self.limit = limit
        return self.jobs


class ProcessingReconciliationServiceTestCase(unittest.TestCase):
    def make_settings(self) -> Settings:
        return Settings(
            _env_file=None,
            PROCESSING_RECONCILIATION_INTERVAL_SECONDS=60,
            PROCESSING_RECONCILIATION_STALE_SECONDS=120,
            PROCESSING_RECONCILIATION_BATCH_SIZE=25,
        )

    def test_republishes_stale_pending_jobs_and_records_cooldown_metadata(self) -> None:
        job = SimpleNamespace(id="job-1", meeting_id="meeting-1", payload={"meetingId": "meeting-1"})
        session = FakeSession()
        locks = FakeLockProvider()
        queue = FakeQueueProvider()
        jobs = FakeJobRepository([job])
        service = ProcessingReconciliationService(
            session=session,
            settings=self.make_settings(),
            lock_provider=locks,
            queue_provider=queue,
            jobs=jobs,
        )

        result = service.reconcile()

        self.assertEqual(result, {"status": "completed", "scanned": 1, "republished": 1, "failed": 0})
        self.assertEqual(queue.enqueued, [("job-1", "meeting-1")])
        self.assertEqual(job.payload["reconciliation"]["republishCount"], 1)
        self.assertTrue(job.payload["reconciliation"]["lastRepublishedAt"])
        self.assertEqual(jobs.limit, 25)
        self.assertEqual(session.commits, 1)
        self.assertEqual(locks.released, [(service.lock_key, "token")])

    def test_skips_run_when_another_reconciler_holds_the_lock(self) -> None:
        session = FakeSession()
        queue = FakeQueueProvider()
        service = ProcessingReconciliationService(
            session=session,
            settings=self.make_settings(),
            lock_provider=FakeLockProvider(available=False),
            queue_provider=queue,
            jobs=FakeJobRepository([]),
        )

        result = service.reconcile()

        self.assertEqual(result, {"status": "locked", "scanned": 0, "republished": 0, "failed": 0})
        self.assertEqual(queue.enqueued, [])
        self.assertEqual(session.commits, 0)

    def test_broker_failure_leaves_job_eligible_for_a_later_reconciliation(self) -> None:
        job = SimpleNamespace(id="job-1", meeting_id="meeting-1", payload={"meetingId": "meeting-1"})
        session = FakeSession()
        service = ProcessingReconciliationService(
            session=session,
            settings=self.make_settings(),
            lock_provider=FakeLockProvider(),
            queue_provider=FakeQueueProvider(failing_job_id="job-1"),
            jobs=FakeJobRepository([job]),
        )

        result = service.reconcile()

        self.assertEqual(result, {"status": "completed", "scanned": 1, "republished": 0, "failed": 1})
        self.assertNotIn("reconciliation", job.payload)
        self.assertEqual(session.commits, 1)


if __name__ == "__main__":
    unittest.main()
