import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import delete

from backend.configs.database import SessionLocal
from backend.configs.settings import Settings
from backend.models.core_models import User
from backend.models.enums import MeetingStatus
from backend.models.meeting_models import MeetingRetrievalSnapshot
from backend.providers.vector_provider import VectorProviderError
from backend.repositories.auth_repository import AuthRepository
from backend.repositories.meeting_repository import (
    MeetingAssetRepository,
    MeetingIntelligenceResultRepository,
    MeetingRepository,
)
from backend.repositories.retrieval_repository import MeetingChunkRepository
from backend.services.processing_pipeline_service import ProcessingPipelineService
from backend.services.processing_reconciliation_service import ProcessingReconciliationService
from backend.services.retrieval.index_service import RetrievalIndexService
from backend.tasks.processing_tasks import repair_retrieval_index
from backend.tests.fakes import TestEmbeddingProvider
from backend.tests.processing.test_processing_pipeline_service import (
    FakeAnalysisProvider,
    FakeLockProvider as PipelineLockProvider,
    FakeTranscriptionProvider,
)


class FakeLockProvider:
    def __init__(self) -> None:
        self.released: list[tuple[str, str]] = []

    def acquire(self, key: str) -> str:
        return f"lock:{key}"

    def release(self, key: str, token: str) -> None:
        self.released.append((key, token))


class SuccessfulIndexService:
    rebuild_calls = 0

    def __init__(self, session, vector_provider=None) -> None:
        self.results = MeetingIntelligenceResultRepository(session)
        self.last_vector_metadata = {"status": "upserted"}

    def rebuild_for_result(self, result):
        type(self).rebuild_calls += 1
        return []


class FailingIndexService(SuccessfulIndexService):
    def rebuild_for_result(self, result):
        raise RuntimeError("temporary vector outage")


class RepairQueue:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.repairs: list[tuple[str, str]] = []

    def enqueue_retrieval_repair(self, *, meeting_id: str, repair_token: str) -> None:
        self.repairs.append((meeting_id, repair_token))
        if self.fail:
            raise RuntimeError("broker unavailable")


class NoopChatQueue:
    def enqueue_turn(self, **kwargs) -> None:
        return None


class FailingVectorProvider:
    provider_name = "failing-vector"

    def upsert_chunks(self, chunks):
        raise VectorProviderError("vector unavailable")


class InitialRepairQueue(RepairQueue):
    pass

    def enqueue_memory_sync(self, **kwargs) -> None:
        return None

    def enqueue_memory_revalidation(self, **kwargs) -> None:
        return None


class VectorRepairLifecycleTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.user_id = str(uuid4())
        with SessionLocal() as session:
            AuthRepository(session).upsert_dev_user(
                user_id=self.user_id,
                email=f"{self.user_id}@vector-repair.test",
                display_name="Vector Repair User",
                role="User",
            )
            session.commit()

    def tearDown(self) -> None:
        with SessionLocal() as session:
            session.execute(delete(User).where(User.id == self.user_id))
            session.commit()

    def test_claim_token_fences_start_restore_and_stale_recovery(self) -> None:
        meeting_id = self._create_pending_snapshot()
        with SessionLocal() as session:
            repository = MeetingChunkRepository(session)
            first = repository.claim_repair_for_publish(
                meeting_id=meeting_id,
                lease_seconds=60,
            )
            self.assertIsNotNone(first)
            session.commit()

            self.assertFalse(
                repository.restore_repair_pending_if_owned(
                    meeting_id=meeting_id,
                    token="wrong-token",
                )
            )
            self.assertTrue(
                repository.mark_repair_started_if_owned(
                    meeting_id=meeting_id,
                    token=first.token,
                    lease_seconds=60,
                )
            )
            self.assertFalse(
                repository.mark_repair_started_if_owned(
                    meeting_id=meeting_id,
                    token=first.token,
                    lease_seconds=60,
                )
            )
            snapshot = session.get(MeetingRetrievalSnapshot, meeting_id)
            snapshot.repair_lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            session.commit()

            recovered = repository.claim_stale_repairs(
                updated_before=datetime.now(UTC),
                limit=10,
                lease_seconds=60,
            )
            self.assertEqual(len(recovered), 1)
            self.assertNotEqual(recovered[0].token, first.token)
            self.assertFalse(
                repository.mark_repair_started_if_owned(
                    meeting_id=meeting_id,
                    token=first.token,
                    lease_seconds=60,
                )
            )
            self.assertTrue(
                repository.restore_repair_pending_if_owned(
                    meeting_id=meeting_id,
                    token=recovered[0].token,
                )
            )
            session.commit()

            snapshot = session.get(MeetingRetrievalSnapshot, meeting_id)
            self.assertEqual(snapshot.repair_status, "pending")
            self.assertIsNone(snapshot.repair_lease_token)

    def test_task_redelivery_is_noop_after_success(self) -> None:
        meeting_id = self._create_pending_snapshot()
        with SessionLocal() as session:
            claim = MeetingChunkRepository(session).claim_repair_for_publish(
                meeting_id=meeting_id,
                lease_seconds=60,
            )
            session.commit()

        locks = FakeLockProvider()
        SuccessfulIndexService.rebuild_calls = 0
        with (
            patch("backend.tasks.processing_tasks.get_redis_lock_provider", return_value=locks),
            patch("backend.tasks.processing_tasks.get_vector_provider", return_value=SimpleNamespace()),
            patch("backend.tasks.processing_tasks.RetrievalIndexService", SuccessfulIndexService),
        ):
            first = repair_retrieval_index.run(meeting_id=meeting_id, repair_token=claim.token)
            second = repair_retrieval_index.run(meeting_id=meeting_id, repair_token=claim.token)

        self.assertEqual(first["status"], "repaired")
        self.assertEqual(second["status"], "noop")
        self.assertEqual(SuccessfulIndexService.rebuild_calls, 1)
        with SessionLocal() as session:
            snapshot = session.get(MeetingRetrievalSnapshot, meeting_id)
            self.assertEqual(snapshot.repair_status, "none")
            self.assertEqual(snapshot.repair_attempt_count, 1)
            self.assertIsNone(snapshot.repair_lease_token)

    def test_reconciler_restores_failed_publish_and_publishes_new_claim(self) -> None:
        meeting_id = self._create_pending_snapshot()
        stale_before = datetime.now(UTC) - timedelta(minutes=1)
        settings = Settings(
            _env_file=None,
            PROCESSING_RECONCILIATION_STALE_SECONDS=60,
            PROCESSING_RECONCILIATION_BATCH_SIZE=10,
        )

        with SessionLocal() as session:
            snapshot = session.get(MeetingRetrievalSnapshot, meeting_id)
            snapshot.updated_at = datetime.now(UTC) - timedelta(minutes=10)
            session.commit()
            failed_queue = RepairQueue(fail=True)
            result = ProcessingReconciliationService(
                session=session,
                settings=settings,
                queue_provider=failed_queue,
                chat_queue_provider=NoopChatQueue(),
            ).reconcile_chat_work(stale_before=stale_before)
            session.expire_all()
            snapshot = session.get(MeetingRetrievalSnapshot, meeting_id)
            self.assertEqual(result["retrieval_repair_queued"], 0)
            self.assertEqual(snapshot.repair_status, "pending")
            self.assertIsNone(snapshot.repair_lease_token)
            failed_token = failed_queue.repairs[0][1]

            snapshot.updated_at = datetime.now(UTC) - timedelta(minutes=10)
            session.commit()
            successful_queue = RepairQueue()
            result = ProcessingReconciliationService(
                session=session,
                settings=settings,
                queue_provider=successful_queue,
                chat_queue_provider=NoopChatQueue(),
            ).reconcile_chat_work(stale_before=stale_before)
            session.expire_all()
            snapshot = session.get(MeetingRetrievalSnapshot, meeting_id)

        self.assertEqual(result["retrieval_repair_queued"], 1)
        self.assertEqual(len(successful_queue.repairs), 1)
        self.assertEqual(successful_queue.repairs[0][0], meeting_id)
        self.assertNotEqual(successful_queue.repairs[0][1], failed_token)
        self.assertEqual(snapshot.repair_status, "queued")
        self.assertEqual(snapshot.repair_lease_token, successful_queue.repairs[0][1])

    def test_initial_publish_failure_restores_pending_claim(self) -> None:
        meeting_id = self._create_uploaded_meeting()
        queue = InitialRepairQueue(fail=True)
        with SessionLocal() as session:
            retrieval_index = RetrievalIndexService(
                session,
                embedding_provider=TestEmbeddingProvider(dimensions=8),
                vector_provider=FailingVectorProvider(),
            )
            service = ProcessingPipelineService(
                session,
                lock_provider=PipelineLockProvider(),
                transcription_provider=FakeTranscriptionProvider(),
                analysis_provider=FakeAnalysisProvider(),
                retrieval_index=retrieval_index,
            )
            with patch(
                "backend.providers.queue_provider.get_processing_queue_provider",
                return_value=queue,
            ):
                response = service.process_meeting(meeting_id=meeting_id)
            session.expire_all()
            snapshot = session.get(MeetingRetrievalSnapshot, meeting_id)

        self.assertEqual(response["status"], "succeeded")
        self.assertEqual(len(queue.repairs), 1)
        self.assertEqual(queue.repairs[0][0], meeting_id)
        self.assertEqual(snapshot.repair_status, "pending")
        self.assertIsNone(snapshot.repair_lease_token)

    def test_task_failure_requeues_same_token_for_retry(self) -> None:
        meeting_id = self._create_pending_snapshot()
        with SessionLocal() as session:
            claim = MeetingChunkRepository(session).claim_repair_for_publish(
                meeting_id=meeting_id,
                lease_seconds=60,
            )
            session.commit()

        with (
            patch("backend.tasks.processing_tasks.get_redis_lock_provider", return_value=FakeLockProvider()),
            patch("backend.tasks.processing_tasks.get_vector_provider", return_value=SimpleNamespace()),
            patch("backend.tasks.processing_tasks.RetrievalIndexService", FailingIndexService),
            self.assertRaises(RuntimeError),
        ):
            repair_retrieval_index.run(meeting_id=meeting_id, repair_token=claim.token)

        with SessionLocal() as session:
            snapshot = session.get(MeetingRetrievalSnapshot, meeting_id)
            self.assertEqual(snapshot.repair_status, "queued")
            self.assertEqual(snapshot.repair_lease_token, claim.token)
            self.assertEqual(snapshot.repair_attempt_count, 1)
            self.assertIn("RuntimeError", snapshot.last_error)

    def _create_pending_snapshot(self) -> str:
        with SessionLocal() as session:
            meetings = MeetingRepository(session)
            meeting = meetings.create(user_id=self.user_id, title="Vector repair lifecycle")
            meetings.update_status(meeting, MeetingStatus.READY)
            result = MeetingIntelligenceResultRepository(session).upsert(
                meeting_id=meeting.id,
                schema_version="meeting-intelligence-result.v2",
                provider_name="test",
                provider_model="test",
                result_json={"schemaVersion": "meeting-intelligence-result.v2"},
            )
            MeetingChunkRepository(session).upsert_snapshot(
                meeting_id=meeting.id,
                intelligence_result_id=result.id,
                index_generation=f"generation:{meeting.id}",
                embedding_identity="test:embedding:v1:8",
                retrieval_contract="v2",
                chunk_count=0,
                error="vector_repair_pending",
            )
            session.commit()
            return meeting.id

    def _create_uploaded_meeting(self) -> str:
        with SessionLocal() as session:
            meeting = MeetingRepository(session).create(
                user_id=self.user_id,
                title="Vector repair initial publish",
            )
            MeetingRepository(session).update_status(meeting, MeetingStatus.UPLOADED)
            MeetingAssetRepository(session).create(
                meeting_id=meeting.id,
                user_id=self.user_id,
                object_key=f"users/{self.user_id}/meetings/{meeting.id}/uploads/test.wav",
                file_name="test.wav",
                content_type="audio/wav",
                size_bytes=100,
                idempotency_key="upload",
            )
            session.commit()
            return meeting.id


if __name__ == "__main__":
    unittest.main()
