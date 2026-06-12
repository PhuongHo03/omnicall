import unittest
from io import BytesIO
from uuid import uuid4

from sqlalchemy import delete, func, select
from starlette.datastructures import Headers, UploadFile

from backend.configs.database import SessionLocal
from backend.configs.settings import get_settings
from backend.dependencies.auth import CurrentUserContext
from backend.dtos.meeting_dto import MeetingCreateRequest
from backend.models.core_models import User, Workspace
from backend.models.enums import MeetingStatus, ProcessingJobStatus
from backend.models.meeting_models import MeetingChunkRecord, MeetingInsightRecord, MeetingIntelligenceResult, TranscriptSegmentRecord
from backend.providers.analysis_provider import SCHEMA_VERSION, LocalAnalysisProvider
from backend.providers.transcript_types import TranscriptSegment
from backend.repositories.auth_repository import AuthRepository
from backend.repositories.meeting_repository import MeetingRepository, ProcessingJobRepository
from backend.services.meeting_service import MeetingService
from backend.services.processing_pipeline_service import ProcessingPipelineService


class FakeStorageProvider:
    def put_object(self, *, object_key, data, size_bytes, content_type) -> None:
        return None


class FakeQueueProvider:
    def enqueue_meeting_processing(self, *, job_id: str, meeting_id: str) -> None:
        return None


class FakeLockProvider:
    def __init__(self, locked: bool = False) -> None:
        self.locked = locked
        self.released: list[tuple[str, str]] = []

    def acquire(self, key: str, ttl_seconds: int | None = None) -> str | None:
        return None if self.locked else "lock-token"

    def release(self, key: str, token: str) -> None:
        self.released.append((key, token))


class CountingTranscriptionProvider:
    provider_name = "test-transcription"
    provider_model = "test-model"
    last_provider_name = provider_name
    last_provider_model = provider_model

    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, meeting, asset) -> list[TranscriptSegment]:
        self.calls += 1
        return [
            TranscriptSegment(
                id="seg-001",
                speaker="Speaker 1",
                start_ms=0,
                end_ms=5000,
                text="The team agreed to keep processing idempotent.",
                confidence=0.9,
            )
        ]


class CountingAnalysisProvider(LocalAnalysisProvider):
    provider_name = "test-analysis"
    provider_model = "test-model"
    last_provider_name = provider_name
    last_provider_model = provider_model

    def __init__(self) -> None:
        self.calls = 0

    def build_result(self, *, meeting, asset, transcript_segments):
        self.calls += 1
        result = super().build_result(meeting=meeting, asset=asset, transcript_segments=transcript_segments)
        result["source"]["analysisProvider"] = self.provider_name
        result["source"]["analysisModel"] = self.provider_model
        return result


class BrokenAnalysisProvider:
    provider_name = "broken-analysis"
    provider_model = "broken-model"
    last_provider_name = provider_name
    last_provider_model = provider_model

    def build_result(self, *, meeting, asset, transcript_segments):
        raise ValueError("invalid provider output")


class ProcessingPipelineServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.user_id = str(uuid4())
        self.workspace_id = str(uuid4())
        self.context = CurrentUserContext(
            user_id=self.user_id,
            workspace_id=self.workspace_id,
            role="owner",
        )
        with SessionLocal() as session:
            AuthRepository(session).upsert_dev_context(
                user_id=self.user_id,
                workspace_id=self.workspace_id,
                email=f"{self.user_id}@test.omnicall",
                display_name="Pipeline Test User",
                workspace_name="Pipeline Test Workspace",
            )
            session.commit()

    def tearDown(self) -> None:
        with SessionLocal() as session:
            session.execute(delete(Workspace).where(Workspace.id == self.workspace_id))
            session.execute(delete(User).where(User.id == self.user_id))
            session.commit()

    def create_queued_job(self) -> tuple[str, str]:
        with SessionLocal() as session:
            meeting_service = MeetingService(session, FakeStorageProvider(), FakeQueueProvider(), get_settings())
            meeting = meeting_service.create_meeting(
                self.context,
                MeetingCreateRequest(title="Pipeline idempotency test", language="vi"),
            )
            upload = UploadFile(
                file=BytesIO(b"RIFF....WAVEfmt "),
                filename="meeting.wav",
                headers=Headers({"content-type": "audio/wav"}),
            )
            meeting_service.upload_asset(self.context, meeting.id, upload, "upload-pipeline-test")
            job = meeting_service.queue_processing(self.context, meeting.id, "process-pipeline-test")
            return meeting.id, job.id

    def test_succeeded_job_is_skipped_without_duplicate_processing(self) -> None:
        meeting_id, job_id = self.create_queued_job()
        transcription_provider = CountingTranscriptionProvider()
        analysis_provider = CountingAnalysisProvider()

        with SessionLocal() as session:
            service = ProcessingPipelineService(
                session=session,
                lock_provider=FakeLockProvider(),
                transcription_provider=transcription_provider,
                analysis_provider=analysis_provider,
            )
            first_result = service.process_meeting(job_id=job_id, meeting_id=meeting_id)
            second_result = service.process_meeting(job_id=job_id, meeting_id=meeting_id)

            job = ProcessingJobRepository(session).get(job_id)
            result_count = session.scalar(
                select(func.count())
                .select_from(MeetingIntelligenceResult)
                .where(
                    MeetingIntelligenceResult.meeting_id == meeting_id,
                    MeetingIntelligenceResult.schema_version == SCHEMA_VERSION,
                )
            )
            segment_count = session.scalar(
                select(func.count()).select_from(TranscriptSegmentRecord).where(TranscriptSegmentRecord.meeting_id == meeting_id)
            )
            insight_count = session.scalar(
                select(func.count()).select_from(MeetingInsightRecord).where(MeetingInsightRecord.meeting_id == meeting_id)
            )
            chunk_count = session.scalar(
                select(func.count()).select_from(MeetingChunkRecord).where(MeetingChunkRecord.meeting_id == meeting_id)
            )

        self.assertEqual(first_result["status"], "succeeded")
        self.assertEqual(second_result["status"], "skipped")
        self.assertEqual(transcription_provider.calls, 1)
        self.assertEqual(analysis_provider.calls, 1)
        self.assertEqual(job.status, ProcessingJobStatus.SUCCEEDED)
        self.assertEqual(job.attempts, 1)
        self.assertEqual(job.payload["providerMetadata"]["analysisProvider"], "test-analysis")
        self.assertEqual(job.payload["retrievalMetadata"]["embeddingProvider"], "local-hash-embedding")
        self.assertGreater(job.payload["retrievalMetadata"]["chunkCount"], 0)
        self.assertEqual(result_count, 1)
        self.assertEqual(segment_count, 1)
        self.assertGreater(insight_count, 0)
        self.assertGreater(chunk_count, 0)

    def test_locked_meeting_does_not_mutate_pending_job(self) -> None:
        meeting_id, job_id = self.create_queued_job()
        transcription_provider = CountingTranscriptionProvider()
        analysis_provider = CountingAnalysisProvider()

        with SessionLocal() as session:
            service = ProcessingPipelineService(
                session=session,
                lock_provider=FakeLockProvider(locked=True),
                transcription_provider=transcription_provider,
                analysis_provider=analysis_provider,
            )
            result = service.process_meeting(job_id=job_id, meeting_id=meeting_id)
            job = ProcessingJobRepository(session).get(job_id)
            meeting = MeetingRepository(session).get_for_workspace(meeting_id, self.workspace_id)

        self.assertEqual(result["status"], "locked")
        self.assertEqual(job.status, ProcessingJobStatus.PENDING)
        self.assertEqual(meeting.status, MeetingStatus.QUEUED)
        self.assertEqual(transcription_provider.calls, 0)
        self.assertEqual(analysis_provider.calls, 0)

    def test_provider_failure_marks_job_and_meeting_failed_with_safe_reason(self) -> None:
        meeting_id, job_id = self.create_queued_job()

        with SessionLocal() as session:
            service = ProcessingPipelineService(
                session=session,
                lock_provider=FakeLockProvider(),
                transcription_provider=CountingTranscriptionProvider(),
                analysis_provider=BrokenAnalysisProvider(),
            )
            result = service.process_meeting(job_id=job_id, meeting_id=meeting_id)
            job = ProcessingJobRepository(session).get(job_id)
            meeting = MeetingRepository(session).get_for_workspace(meeting_id, self.workspace_id)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(job.status, ProcessingJobStatus.FAILED)
        self.assertEqual(job.safe_failure_reason, "Meeting processing failed. Please retry later.")
        self.assertIn("invalid provider output", job.internal_error)
        self.assertEqual(meeting.status, MeetingStatus.FAILED)
        self.assertEqual(meeting.failure_reason, "Meeting processing failed. Please retry later.")

    def test_failed_job_can_transition_through_retrying_to_succeeded(self) -> None:
        meeting_id, job_id = self.create_queued_job()

        with SessionLocal() as session:
            jobs = ProcessingJobRepository(session)
            meetings = MeetingRepository(session)
            job = jobs.get(job_id)
            meeting = meetings.get_for_workspace(meeting_id, self.workspace_id)
            jobs.update_status(
                job,
                ProcessingJobStatus.FAILED,
                safe_failure_reason="Previous provider error.",
                internal_error="provider_error",
            )
            meetings.update_status(meeting, MeetingStatus.FAILED, "Previous provider error.")
            session.commit()

        with SessionLocal() as session:
            service = ProcessingPipelineService(
                session=session,
                lock_provider=FakeLockProvider(),
                transcription_provider=CountingTranscriptionProvider(),
                analysis_provider=CountingAnalysisProvider(),
            )
            result = service.process_meeting(job_id=job_id, meeting_id=meeting_id)
            job = ProcessingJobRepository(session).get(job_id)
            meeting = MeetingRepository(session).get_for_workspace(meeting_id, self.workspace_id)

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(job.status, ProcessingJobStatus.SUCCEEDED)
        self.assertEqual(job.attempts, 1)
        self.assertEqual(meeting.status, MeetingStatus.READY)

    def test_result_validation_rejects_unknown_citation_references(self) -> None:
        invalid_result = {
            "schemaVersion": "meeting-intelligence-result.v1",
            "meeting": {"id": "meeting-id"},
            "source": {},
            "transcript": {
                "segments": [
                    {"id": "seg-001", "speaker": "Speaker 1", "startMs": 0, "endMs": 1000, "text": "Hello"}
                ]
            },
            "summary": {"executive": "Summary"},
            "analysis": {"actionItems": [{"text": "Do thing", "citationIds": ["cite-missing"]}]},
            "citations": [{"id": "cite-001", "segmentIds": ["seg-001"], "startMs": 0, "endMs": 1000}],
            "quality": {"coverage": "partial", "warnings": [], "confidence": 0.5},
        }

        with self.assertRaisesRegex(ValueError, "unknown citation"):
            ProcessingPipelineService._validate_result_json(invalid_result)


if __name__ == "__main__":
    unittest.main()
