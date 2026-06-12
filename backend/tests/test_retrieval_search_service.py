import unittest
from uuid import uuid4

from sqlalchemy import delete

from backend.configs.database import SessionLocal
from backend.models.core_models import User, Workspace
from backend.models.enums import MeetingStatus, ProcessingJobStatus
from backend.providers.analysis_provider import SCHEMA_VERSION
from backend.providers.embedding_provider import LocalHashEmbeddingProvider
from backend.providers.vector_provider import VectorProviderError, VectorSearchHit
from backend.repositories.auth_repository import AuthRepository
from backend.repositories.meeting_repository import MeetingIntelligenceResultRepository, MeetingRepository, ProcessingJobRepository
from backend.repositories.retrieval_repository import MeetingChunkRepository
from backend.services.retrieval_search_service import RetrievalSearchService


class FakeVectorProvider:
    enabled = True
    provider_name = "fake-vector"

    def __init__(self, hits: list[VectorSearchHit]) -> None:
        self.hits = hits

    def upsert_chunks(self, chunks) -> dict:
        return {"provider": self.provider_name, "status": "upserted", "chunkCount": len(chunks)}

    def search_chunk_ids(self, *, workspace_id: str, meeting_id: str, query_vector: list[float], limit: int) -> list[VectorSearchHit]:
        return self.hits[:limit]


class BrokenVectorProvider:
    enabled = True
    provider_name = "broken-vector"

    def upsert_chunks(self, chunks) -> dict:
        raise VectorProviderError("vector unavailable")

    def search_chunk_ids(self, *, workspace_id: str, meeting_id: str, query_vector: list[float], limit: int) -> list[VectorSearchHit]:
        raise VectorProviderError("vector unavailable")


class RetrievalSearchServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.user_id = str(uuid4())
        self.workspace_id = str(uuid4())
        with SessionLocal() as session:
            AuthRepository(session).upsert_dev_context(
                user_id=self.user_id,
                workspace_id=self.workspace_id,
                email=f"{self.user_id}@test.omnicall",
                display_name="Retrieval Search Test User",
                workspace_name="Retrieval Search Test Workspace",
            )
            session.commit()

    def tearDown(self) -> None:
        with SessionLocal() as session:
            session.execute(delete(Workspace).where(Workspace.id == self.workspace_id))
            session.execute(delete(User).where(User.id == self.user_id))
            session.commit()

    def create_meeting_chunks(self) -> str:
        with SessionLocal() as session:
            meeting_repo = MeetingRepository(session)
            job_repo = ProcessingJobRepository(session)
            result_repo = MeetingIntelligenceResultRepository(session)
            meeting = meeting_repo.create(
                workspace_id=self.workspace_id,
                user_id=self.user_id,
                title="Retrieval search meeting",
                language="vi",
            )
            meeting_repo.update_status(meeting, MeetingStatus.READY)
            job = job_repo.create(
                workspace_id=self.workspace_id,
                meeting_id=meeting.id,
                idempotency_key=f"retrieval-search-{uuid4()}",
                payload={"meetingId": meeting.id},
                status=ProcessingJobStatus.SUCCEEDED,
            )
            result = result_repo.upsert(
                workspace_id=self.workspace_id,
                meeting_id=meeting.id,
                processing_job_id=job.id,
                schema_version=SCHEMA_VERSION,
                provider_name="test",
                provider_model="test",
                result_json={"schemaVersion": SCHEMA_VERSION},
            )
            provider = LocalHashEmbeddingProvider(dimensions=8)
            action_text = "Bob must index action items by Friday."
            risk_text = "Risk is low quality audio reducing answer confidence."
            MeetingChunkRepository(session).replace_for_result(
                workspace_id=self.workspace_id,
                meeting_id=meeting.id,
                intelligence_result_id=result.id,
                chunks=[
                    _chunk("analysis.actionItems-001", "analysis.actionItems", action_text, provider),
                    _chunk("analysis.risks-001", "analysis.risks", risk_text, provider),
                ],
            )
            session.commit()
            return meeting.id

    def test_vector_hits_are_revalidated_against_postgres_scope(self) -> None:
        meeting_id = self.create_meeting_chunks()
        vector_provider = FakeVectorProvider(
            [
                VectorSearchHit(chunk_id="analysis.risks-001", score=0.93),
                VectorSearchHit(chunk_id="missing-or-cross-workspace", score=0.91),
            ]
        )

        with SessionLocal() as session:
            service = RetrievalSearchService(
                session,
                embedding_provider=LocalHashEmbeddingProvider(dimensions=8),
                vector_provider=vector_provider,
            )
            results = service.search_meeting(
                workspace_id=self.workspace_id,
                meeting_id=meeting_id,
                query="What risk affects confidence?",
            )

        self.assertEqual([result.record.chunk_id for result in results], ["analysis.risks-001"])
        self.assertEqual(results[0].score, 0.93)

    def test_broken_vector_provider_falls_back_to_postgres_search(self) -> None:
        meeting_id = self.create_meeting_chunks()
        with SessionLocal() as session:
            service = RetrievalSearchService(
                session,
                embedding_provider=LocalHashEmbeddingProvider(dimensions=8),
                vector_provider=BrokenVectorProvider(),
            )
            results = service.search_meeting(
                workspace_id=self.workspace_id,
                meeting_id=meeting_id,
                query="Who must index action items by Friday?",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.chunk_id, "analysis.actionItems-001")

    def test_local_embedding_vector_hits_without_text_evidence_are_filtered(self) -> None:
        meeting_id = self.create_meeting_chunks()
        vector_provider = FakeVectorProvider(
            [
                VectorSearchHit(chunk_id="analysis.risks-001", score=0.99),
            ]
        )

        with SessionLocal() as session:
            service = RetrievalSearchService(
                session,
                embedding_provider=LocalHashEmbeddingProvider(dimensions=8),
                vector_provider=vector_provider,
            )
            results = service.search_meeting(
                workspace_id=self.workspace_id,
                meeting_id=meeting_id,
                query="What is tomorrow's Bitcoin price?",
            )

        self.assertEqual(results, [])


def _chunk(chunk_id: str, section_type: str, text: str, provider: LocalHashEmbeddingProvider) -> dict:
    embedding = provider.embed_text(text)
    return {
        "chunkId": chunk_id,
        "sourceType": "structured",
        "sectionType": section_type,
        "sourceId": chunk_id,
        "jsonPointer": f"/analysis/{section_type.split('.')[-1]}/0",
        "text": text,
        "citationIds": ["cite-001"],
        "segmentIds": ["seg-001"],
        "startMs": 0,
        "endMs": 1000,
        "tokenCount": len(text.split()),
        "embedding": embedding.vector,
        "visibility": "workspace",
        "metadata": {
            "priority": 50,
            "embeddingProvider": embedding.provider_name,
            "embeddingModel": embedding.model_name,
        },
    }


if __name__ == "__main__":
    unittest.main()
