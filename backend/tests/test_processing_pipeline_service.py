import unittest
from uuid import uuid4

from sqlalchemy import delete, select

from backend.configs.database import SessionLocal
from backend.models.core_models import User
from backend.models.enums import MeetingStatus, ProcessingJobStatus
from backend.models.meeting_models import MeetingChunkRecord, MeetingIntelligenceResult
from backend.providers.analysis_provider import SCHEMA_VERSION
from backend.providers.transcript_types import TranscriptSegment
from backend.providers.vector_provider import NoopVectorProvider
from backend.repositories.auth_repository import AuthRepository
from backend.repositories.meeting_repository import MeetingAssetRepository, MeetingRepository, ProcessingJobRepository
from backend.services.processing_pipeline_service import ProcessingPipelineService
from backend.services.retrieval_index_service import RetrievalIndexService
from backend.tests.fakes import TestEmbeddingProvider, TestGuardrailProvider


class FakeLockProvider:
    def acquire(self, lock_key: str) -> str:
        return f"token:{lock_key}"

    def release(self, lock_key: str, token: str) -> None:
        return None


class FakeTranscriptionProvider:
    provider_name = "fake-transcription"
    provider_model = "fake-transcription-model"
    last_provider_name = "fake-asr"
    last_provider_model = "fake-asr-model"

    def transcribe(self, meeting, asset) -> list[TranscriptSegment]:
        return [
            TranscriptSegment(
                id="seg-001",
                speaker="Alice",
                start_ms=0,
                end_ms=3000,
                text="Use processed JSON as the source for meeting chatbot retrieval.",
                confidence=0.9,
            )
        ]


class FakeAnalysisProvider:
    provider_name = "fake-analysis"
    provider_model = "fake-analysis-model"
    last_provider_name = "fake-analysis"
    last_provider_model = "fake-analysis-model"

    def build_result(self, *, meeting, asset, transcript_segments: list[TranscriptSegment]) -> dict:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "source": {"analysisProvider": self.provider_name},
            "meeting": {"id": meeting.id, "title": meeting.title},
            "transcript": {
                "segments": [
                    {
                        "id": segment.id,
                        "speaker": segment.speaker,
                        "startMs": segment.start_ms,
                        "endMs": segment.end_ms,
                        "text": segment.text,
                        "confidence": segment.confidence,
                    }
                    for segment in transcript_segments
                ]
            },
            "summary": {
                "executive": "The meeting agreed to use processed JSON for chatbot retrieval.",
                "detailed": [{"title": "RAG", "text": "Processed JSON is the retrieval source.", "citationIds": ["cite-001"]}],
                "keyPoints": [{"text": "Index JSON sections for RAG.", "citationIds": ["cite-001"]}],
            },
            "analysis": {
                "decisions": [{"text": "Use the JSON result as the RAG source.", "citationIds": ["cite-001"]}],
                "actionItems": [{"owner": "Team", "task": "Index processed JSON.", "citationIds": ["cite-001"]}],
                "timeline": [],
                "risks": [],
                "emptySections": {"risks": "No risk evidence."},
            },
            "citations": [{"id": "cite-001", "segmentIds": ["seg-001"], "startMs": 0, "endMs": 3000}],
            "quality": {"coverage": "complete", "warnings": [], "confidence": 0.9},
        }


class ProcessingPipelineServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.user_id = str(uuid4())
        with SessionLocal() as session:
            AuthRepository(session).upsert_dev_user(
                user_id=self.user_id,
                email=f"{self.user_id}@pipeline.test",
                display_name="Pipeline User",
                role="User",
            )
            session.commit()

    def tearDown(self) -> None:
        with SessionLocal() as session:
            session.execute(delete(User).where(User.id == self.user_id))
            session.commit()

    def test_pipeline_persists_one_json_result_and_rag_chunks(self) -> None:
        meeting_id, job_id = self._create_uploaded_meeting_and_job()
        with SessionLocal() as session:
            retrieval_index = RetrievalIndexService(
                session,
                embedding_provider=TestEmbeddingProvider(dimensions=8),
                vector_provider=NoopVectorProvider(),
            )
            service = ProcessingPipelineService(
                session,
                lock_provider=FakeLockProvider(),
                transcription_provider=FakeTranscriptionProvider(),
                analysis_provider=FakeAnalysisProvider(),
                guardrail_provider=TestGuardrailProvider(),
                retrieval_index=retrieval_index,
            )

            response = service.process_meeting(job_id=job_id, meeting_id=meeting_id)
            meeting = MeetingRepository(session).get(meeting_id)
            job = ProcessingJobRepository(session).get(job_id)
            results = list(
                session.scalars(select(MeetingIntelligenceResult).where(MeetingIntelligenceResult.meeting_id == meeting_id)).all()
            )
            chunks = list(session.scalars(select(MeetingChunkRecord).where(MeetingChunkRecord.meeting_id == meeting_id)).all())

        self.assertEqual(response["status"], "succeeded")
        self.assertEqual(meeting.status, MeetingStatus.READY)
        self.assertEqual(job.status, ProcessingJobStatus.SUCCEEDED)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].result_json["transcript"]["segments"][0]["id"], "seg-001")
        self.assertGreaterEqual(len(chunks), 3)

    def _create_uploaded_meeting_and_job(self) -> tuple[str, str]:
        with SessionLocal() as session:
            meeting = MeetingRepository(session).create(user_id=self.user_id, title="Pipeline test")
            MeetingAssetRepository(session).create(
                meeting_id=meeting.id,
                user_id=self.user_id,
                object_key=f"users/{self.user_id}/meetings/{meeting.id}/uploads/test.txt",
                file_name="test.txt",
                content_type="text/plain",
                size_bytes=100,
                idempotency_key="upload",
            )
            job = ProcessingJobRepository(session).create(
                meeting_id=meeting.id,
                idempotency_key="process",
                payload={"meetingId": meeting.id},
            )
            session.commit()
            return meeting.id, job.id


if __name__ == "__main__":
    unittest.main()
