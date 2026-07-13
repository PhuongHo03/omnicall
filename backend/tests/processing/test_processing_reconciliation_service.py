import unittest
from types import SimpleNamespace

from backend.configs.settings import Settings
from backend.services.processing_reconciliation_service import ProcessingReconciliationService


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1

    def query(self, model):
        return self

    def filter(self, *criteria):
        return self

    def all(self):
        return []


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
    def __init__(self, *, failing_meeting_id: str | None = None) -> None:
        self.failing_meeting_id = failing_meeting_id
        self.enqueued: list[str] = []

    def enqueue_meeting_processing(self, *, meeting_id: str) -> None:
        if meeting_id == self.failing_meeting_id:
            raise RuntimeError("broker unavailable")
        self.enqueued.append(meeting_id)


class FakeMeetingRepository:
    def __init__(self, meetings: list[SimpleNamespace]) -> None:
        self.meetings = meetings
        self.updated_before = None
        self.limit = None

    def list_stale_queued(self, *, updated_before, limit: int):
        self.updated_before = updated_before
        self.limit = limit
        return self.meetings


class ProcessingReconciliationServiceTestCase(unittest.TestCase):
    def make_settings(self) -> Settings:
        return Settings(
            _env_file=None,
            PROCESSING_RECONCILIATION_INTERVAL_SECONDS=60,
            PROCESSING_RECONCILIATION_STALE_SECONDS=120,
            PROCESSING_RECONCILIATION_BATCH_SIZE=25,
        )

    def test_republishes_stale_queued_meetings(self) -> None:
        meeting = SimpleNamespace(id="meeting-1")
        session = FakeSession()
        locks = FakeLockProvider()
        queue = FakeQueueProvider()
        meetings = FakeMeetingRepository([meeting])
        service = ProcessingReconciliationService(
            session=session,
            settings=self.make_settings(),
            lock_provider=locks,
            queue_provider=queue,
            meetings=meetings,
        )

        result = service.reconcile()

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["scanned"], 1)
        self.assertEqual(result["republished"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(queue.enqueued, ["meeting-1"])
        self.assertEqual(meetings.limit, 25)
        self.assertGreaterEqual(session.commits, 1)
        self.assertEqual(locks.released, [(service.lock_key, "token")])

    def test_skips_run_when_another_reconciler_holds_the_lock(self) -> None:
        session = FakeSession()
        queue = FakeQueueProvider()
        service = ProcessingReconciliationService(
            session=session,
            settings=self.make_settings(),
            lock_provider=FakeLockProvider(available=False),
            queue_provider=queue,
            meetings=FakeMeetingRepository([]),
        )

        result = service.reconcile()

        self.assertEqual(result, {"status": "locked", "scanned": 0, "republished": 0, "failed": 0})
        self.assertEqual(queue.enqueued, [])
        self.assertEqual(session.commits, 0)

    def test_broker_failure_leaves_meeting_eligible_for_a_later_reconciliation(self) -> None:
        meeting = SimpleNamespace(id="meeting-1")
        session = FakeSession()
        service = ProcessingReconciliationService(
            session=session,
            settings=self.make_settings(),
            lock_provider=FakeLockProvider(),
            queue_provider=FakeQueueProvider(failing_meeting_id="meeting-1"),
            meetings=FakeMeetingRepository([meeting]),
        )

        result = service.reconcile()

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["scanned"], 1)
        self.assertEqual(result["republished"], 0)
        self.assertEqual(result["failed"], 1)
        self.assertGreaterEqual(session.commits, 1)


if __name__ == "__main__":
    unittest.main()
