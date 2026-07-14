import unittest
from uuid import uuid4

from sqlalchemy import delete, select

from backend.configs.database import SessionLocal
from backend.models.core_models import User
from backend.models.enums import MeetingStatus
from backend.models.meeting_models import MeetingChunkRecord, MeetingIntelligenceResult, MeetingTranscriptWindow
from backend.providers.analysis import ANALYSIS_CANDIDATE_SCHEMA_VERSION
from backend.providers.transcript_types import TranscriptSegment
from backend.providers.vector_provider import NoopVectorProvider
from backend.repositories.auth_repository import AuthRepository
from backend.repositories.meeting_repository import MeetingAssetRepository, MeetingRepository
from backend.services.processing_pipeline_service import ProcessingPipelineService
from backend.services.retrieval.index_service import RetrievalIndexService
from backend.tests.fakes import TestEmbeddingProvider


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
    last_voice_metadata = {}

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

    def build_result(self, *, meeting, asset, transcript_segments: list[TranscriptSegment], detected_language=None) -> dict:
        return {
            "schemaVersion": ANALYSIS_CANDIDATE_SCHEMA_VERSION,
            "source": {"analysisProvider": self.provider_name},
            "meeting": {"id": meeting.id, "title": meeting.title},
            "transcript": {
                "segments": [
                    {
                        "id": segment.id,
                        "speakerLabel": segment.speaker,
                        "speaker": segment.speaker,
                        "startMs": segment.start_ms,
                        "endMs": segment.end_ms,
                        "text": segment.text,
                        "confidence": segment.confidence,
                    }
                    for segment in transcript_segments
                ],
                "coverage": {"status": "complete", "coveredAssetIds": [asset.id]},
            },
            "evidence": {
                "citations": [{"id": "cite-001", "segmentIds": ["seg-001"], "startMs": 0, "endMs": 3000, "speakerLabels": ["Alice"], "quote": "Use processed JSON as the source for meeting chatbot retrieval.", "evidenceType": "direct_quote"}]
            },
            "speakers": {
                "speakerCount": 1,
                "identifiedParticipantCount": 1,
                "mentionedOnlyCount": 0,
                "items": [{"label": "Alice", "segmentCount": 1, "totalTalkTimeMs": 3000, "mappedParticipantId": "participant-001", "confidence": 0.9}],
            },
            "participants": [{"id": "participant-001", "displayName": "Alice", "speakerLabels": ["Alice"], "isAttendee": True, "isMentionedOnly": False, "confidence": 0.9, "citationIds": ["cite-001"]}],
            "entities": [{"id": "entity-001", "type": "system", "name": "RAG", "citationIds": ["cite-001"]}],
            "facts": [{"id": "fact-001", "type": "participant_count", "subject": {"type": "meeting", "id": "meeting"}, "predicate": "has_speaker_count", "value": 1, "unit": "people", "confidence": 0.95, "derivedFrom": "speakers", "citationIds": []}],
            "events": [{"id": "event-001", "type": "decision_made", "title": "JSON retrieval source agreed", "participantIds": ["participant-001"], "startMs": 0, "endMs": 3000, "status": "completed", "confidence": 0.9, "citationIds": ["cite-001"]}],
            "relationships": [{"id": "rel-001", "type": "mentions", "from": {"type": "participant", "id": "participant-001"}, "to": {"type": "entity", "id": "entity-001"}, "confidence": 0.9, "citationIds": ["cite-001"]}],
            "topics": [{"id": "topic-001", "title": "RAG", "level": 1, "summary": "Processed JSON is the retrieval source.", "participantIds": ["participant-001"], "factIds": ["fact-001"], "eventIds": ["event-001"], "citationIds": ["cite-001"]}],
            "summaries": {"executive": {"text": "The meeting agreed to use processed JSON for chatbot retrieval.", "topicIds": ["topic-001"], "citationIds": ["cite-001"]}, "topicLevel": [], "timelineLevel": []},
            "actions": [{"id": "action-001", "ownerName": "Team", "task": "Index processed JSON.", "status": "open", "citationIds": ["cite-001"]}],
            "decisions": [{"id": "decision-001", "text": "Use the JSON result as the RAG source.", "citationIds": ["cite-001"]}],
            "risks": [],
            "questions": [],
            "quality": {"coverage": "complete", "warnings": [], "confidence": 0.9},
            "extraction": {"overallConfidence": 0.9, "method": "test", "unsupportedClaims": [], "warnings": []},
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
        meeting_id = self._create_uploaded_meeting()
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
                retrieval_index=retrieval_index,
            )

            response = service.process_meeting(meeting_id=meeting_id)
            meeting = MeetingRepository(session).get(meeting_id)
            results = list(
                session.scalars(select(MeetingIntelligenceResult).where(MeetingIntelligenceResult.meeting_id == meeting_id)).all()
            )
            chunks = list(session.scalars(select(MeetingChunkRecord).where(MeetingChunkRecord.meeting_id == meeting_id)).all())
            windows = list(session.scalars(select(MeetingTranscriptWindow).where(MeetingTranscriptWindow.meeting_id == meeting_id)).all())

        self.assertEqual(response["status"], "succeeded")
        self.assertEqual(meeting.status, MeetingStatus.READY)
        self.assertEqual(meeting.attempts, 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].result_json["transcript"]["segments"][0]["id"], "seg-001")
        self.assertIn("knowledge", results[0].result_json)
        self.assertGreaterEqual(len(results[0].result_json["knowledge"]["records"]), 1)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].status, "succeeded")
        self.assertEqual(windows[0].intelligence_result_id, results[0].id)
        self.assertGreaterEqual(len(chunks), 3)

    def test_success_status_clears_previous_failure_reason(self) -> None:
        with SessionLocal() as session:
            meeting = MeetingRepository(session).create(user_id=self.user_id, title="Failure reason reset")
            MeetingRepository(session).update_status(meeting, MeetingStatus.FAILED, "previous failure")
            MeetingRepository(session).update_status(meeting, MeetingStatus.READY)
            self.assertIsNone(meeting.failure_reason)
            session.rollback()

    def _create_uploaded_meeting(self) -> str:
        with SessionLocal() as session:
            meeting = MeetingRepository(session).create(user_id=self.user_id, title="Pipeline test")
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
