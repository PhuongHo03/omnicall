import unittest
from uuid import uuid4

from sqlalchemy import delete

from backend.configs.database import SessionLocal
from backend.models.core_models import User
from backend.models.enums import MeetingStatus
from backend.providers.analysis_provider import SCHEMA_VERSION
from backend.providers.vector_provider import VectorProviderError, VectorSearchHit
from backend.repositories.auth_repository import AuthRepository
from backend.repositories.meeting_repository import MeetingIntelligenceResultRepository, MeetingRepository
from backend.repositories.retrieval_repository import MeetingChunkRepository
from backend.services.retrieval_search_service import RetrievalSearchService
from backend.tests.fakes import TestEmbeddingProvider


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


class ReverseRerankProvider:
    provider_name = "reverse-rerank"
    model_name = "test-rerank"

    def rerank(self, *, query: str, chunks: list, output_k: int) -> list:
        return list(reversed(chunks))[:output_k]


class RetrievalSearchServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.user_id = str(uuid4())
        self.workspace_id = self.user_id
        with SessionLocal() as session:
            AuthRepository(session).upsert_dev_user(
                user_id=self.user_id,
                email=f"{self.user_id}@test.omnicall",
                display_name="Retrieval Search Test User",
                role="User",
            )
            session.commit()

    def tearDown(self) -> None:
        with SessionLocal() as session:
            session.execute(delete(User).where(User.id == self.user_id))
            session.commit()

    def create_meeting_chunks(self) -> str:
        with SessionLocal() as session:
            meeting_repo = MeetingRepository(session)
            result_repo = MeetingIntelligenceResultRepository(session)
            meeting = meeting_repo.create(
                user_id=self.user_id,
                title="Retrieval search meeting",
            )
            meeting_repo.update_status(meeting, MeetingStatus.READY)
            result = result_repo.upsert(
                meeting_id=meeting.id,
                schema_version=SCHEMA_VERSION,
                provider_name="test",
                provider_model="test",
                result_json={"schemaVersion": SCHEMA_VERSION},
            )
            provider = TestEmbeddingProvider(dimensions=8)
            summary_text = "The meeting covers processed JSON retrieval and chatbot evidence."
            detailed_text = "The customer returned a coat because the size was wrong and the desired size was unavailable."
            key_point_text = "Key point: structured summaries should answer overview questions."
            requirement_text = "The customer requires a refund for a returned coat."
            constraint_text = "The return request was made outside the standard refund timeframe."
            blocker_text = "The first order number was not accepted by the database."
            action_text = "Bob must index action items by Friday."
            risk_text = "Risk is low quality audio reducing answer confidence."
            participant_overview_text = "Participants overview. participant Count: 2. participants: Alice, Bob"
            participant_text = "name: Alice. role: Product owner. details: Alice led the meeting."
            meeting_text = "Meeting metadata. title: Retrieval search meeting. duration Seconds: 120"
            quality_text = "Quality overview. coverage: partial. confidence: 0.74"
            quality_warning_text = "Quality warning: low volume audio may reduce transcript confidence"
            source_text = "Processing source. analysis Provider: llm-analysis. analysis Model: test-analysis-model. llm Provider: test-llm"
            empty_text = "Empty analysis section. section: timeline. reason: No timeline evidence."
            metric_text = "metric: conversion rate target. value: 75 percent."
            glossary_text = "term: RAG. definition: retrieval augmented generation."
            MeetingChunkRepository(session).replace_for_result(
                meeting_id=meeting.id,
                intelligence_result_id=result.id,
                chunks=[
                    _chunk("meeting-metadata", "meeting.metadata", meeting_text, provider, source_type="metadata", priority=5),
                    _chunk("source-processing", "source.processing", source_text, provider, source_type="metadata", priority=35),
                    _chunk("participants-overview", "participants.overview", participant_overview_text, provider, priority=32),
                    _chunk("participants.participant-001", "participants.participant", participant_text, provider, priority=34),
                    _chunk("summary-executive", "summary.executive", summary_text, provider),
                    _chunk("summary.detailed-001", "summary.detailed", detailed_text, provider),
                    _chunk("summary.keyPoints-001", "summary.keyPoints", key_point_text, provider),
                    _chunk("analysis.requirements-001", "analysis.requirements", requirement_text, provider),
                    _chunk("analysis.constraints-001", "analysis.constraints", constraint_text, provider),
                    _chunk("analysis.blockers-001", "analysis.blockers", blocker_text, provider),
                    _chunk("analysis.actionItems-001", "analysis.actionItems", action_text, provider),
                    _chunk("analysis.risks-001", "analysis.risks", risk_text, provider),
                    _chunk("analysis.metrics-001", "analysis.metrics", metric_text, provider, priority=160),
                    _chunk("analysis.glossary-001", "analysis.glossary", glossary_text, provider, priority=170),
                    _chunk("analysis.emptySections-001", "analysis.emptySections", empty_text, provider, priority=180),
                    _chunk("quality-overview", "quality.overview", quality_text, provider, source_type="metadata", priority=190),
                    _chunk("quality.warning-001", "quality.warning", quality_warning_text, provider, source_type="metadata", priority=191),
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
                embedding_provider=TestEmbeddingProvider(dimensions=8),
                vector_provider=vector_provider,
            )
            results = service.search_meeting(
                workspace_id=self.workspace_id,
                meeting_id=meeting_id,
                query="vector lookup smoke",
            )

        self.assertEqual([result.record.chunk_id for result in results], ["analysis.risks-001"])
        self.assertEqual(results[0].score, 0.93)

    def test_broken_vector_provider_falls_back_to_postgres_search(self) -> None:
        meeting_id = self.create_meeting_chunks()
        with SessionLocal() as session:
            service = RetrievalSearchService(
                session,
                embedding_provider=TestEmbeddingProvider(dimensions=8),
                vector_provider=BrokenVectorProvider(),
            )
            results = service.search_meeting(
                workspace_id=self.workspace_id,
                meeting_id=meeting_id,
                query="Who must index action items by Friday?",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.chunk_id, "analysis.actionItems-001")

    def test_vietnamese_overview_question_pins_summary_chunks(self) -> None:
        meeting_id = self.create_meeting_chunks()
        with SessionLocal() as session:
            service = RetrievalSearchService(
                session,
                embedding_provider=TestEmbeddingProvider(dimensions=8),
                vector_provider=BrokenVectorProvider(),
                rerank_provider=ReverseRerankProvider(),
            )
            results = service.search_meeting(
                workspace_id=self.workspace_id,
                meeting_id=meeting_id,
                query="Cuộc họp này bàn về vấn đề gì?",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.chunk_id, "summary-executive")
        self.assertEqual(results[1].record.chunk_id, "summary.detailed-001")
        self.assertEqual(results[2].record.chunk_id, "summary.keyPoints-001")
        self.assertEqual(service.last_rerank_metadata["intentPinnedCount"], 3)

    def test_vietnamese_participant_count_question_pins_participant_chunks(self) -> None:
        meeting_id = self.create_meeting_chunks()
        with SessionLocal() as session:
            service = RetrievalSearchService(
                session,
                embedding_provider=TestEmbeddingProvider(dimensions=8),
                vector_provider=BrokenVectorProvider(),
                rerank_provider=ReverseRerankProvider(),
            )
            results = service.search_meeting(
                workspace_id=self.workspace_id,
                meeting_id=meeting_id,
                query="Cuộc gọi này có bao nhiêu người tham gia?",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.chunk_id, "participants-overview")
        self.assertEqual(results[1].record.chunk_id, "participants.participant-001")
        self.assertEqual(service.last_rerank_metadata["intentPinnedCount"], 2)

    def test_quality_question_pins_quality_chunks(self) -> None:
        meeting_id = self.create_meeting_chunks()
        with SessionLocal() as session:
            service = RetrievalSearchService(
                session,
                embedding_provider=TestEmbeddingProvider(dimensions=8),
                vector_provider=BrokenVectorProvider(),
                rerank_provider=ReverseRerankProvider(),
            )
            results = service.search_meeting(
                workspace_id=self.workspace_id,
                meeting_id=meeting_id,
                query="Chất lượng transcript có cảnh báo gì không?",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.chunk_id, "quality-overview")
        self.assertEqual(results[1].record.chunk_id, "quality.warning-001")

    def test_source_model_question_pins_source_chunks(self) -> None:
        meeting_id = self.create_meeting_chunks()
        with SessionLocal() as session:
            service = RetrievalSearchService(
                session,
                embedding_provider=TestEmbeddingProvider(dimensions=8),
                vector_provider=BrokenVectorProvider(),
                rerank_provider=ReverseRerankProvider(),
            )
            results = service.search_meeting(
                workspace_id=self.workspace_id,
                meeting_id=meeting_id,
                query="Cuộc họp này dùng model nào để phân tích?",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.chunk_id, "source-processing")

    def test_empty_sections_question_pins_empty_section_chunks(self) -> None:
        meeting_id = self.create_meeting_chunks()
        with SessionLocal() as session:
            service = RetrievalSearchService(
                session,
                embedding_provider=TestEmbeddingProvider(dimensions=8),
                vector_provider=BrokenVectorProvider(),
                rerank_provider=ReverseRerankProvider(),
            )
            results = service.search_meeting(
                workspace_id=self.workspace_id,
                meeting_id=meeting_id,
                query="Phần nào thiếu bằng chứng?",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.chunk_id, "analysis.emptySections-001")

    def test_vietnamese_reason_question_pins_detailed_reason_chunks(self) -> None:
        meeting_id = self.create_meeting_chunks()
        with SessionLocal() as session:
            service = RetrievalSearchService(
                session,
                embedding_provider=TestEmbeddingProvider(dimensions=8),
                vector_provider=BrokenVectorProvider(),
                rerank_provider=ReverseRerankProvider(),
            )
            results = service.search_meeting(
                workspace_id=self.workspace_id,
                meeting_id=meeting_id,
                query="Tại sao khách lại muốn đổi trả áo?",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.chunk_id, "summary.detailed-001")
        self.assertEqual(results[1].record.chunk_id, "summary-executive")
        self.assertEqual(results[2].record.chunk_id, "analysis.requirements-001")
        self.assertEqual(service.last_rerank_metadata["intentPinnedCount"], 6)

    def test_vietnamese_return_process_question_pins_return_context(self) -> None:
        meeting_id = self.create_meeting_chunks()
        with SessionLocal() as session:
            service = RetrievalSearchService(
                session,
                embedding_provider=TestEmbeddingProvider(dimensions=8),
                vector_provider=BrokenVectorProvider(),
                rerank_provider=ReverseRerankProvider(),
            )
            results = service.search_meeting(
                workspace_id=self.workspace_id,
                meeting_id=meeting_id,
                query="Khách có thể đổi trả hàng như nào?",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.chunk_id, "summary.detailed-001")
        self.assertEqual(results[1].record.chunk_id, "analysis.requirements-001")
        self.assertEqual(results[2].record.chunk_id, "analysis.constraints-001")
        self.assertEqual(service.last_rerank_metadata["intentPinnedCount"], 5)

    def test_rerank_provider_reorders_vector_candidates(self) -> None:
        meeting_id = self.create_meeting_chunks()
        vector_provider = FakeVectorProvider(
            [
                VectorSearchHit(chunk_id="analysis.risks-001", score=0.99),
                VectorSearchHit(chunk_id="analysis.actionItems-001", score=0.91),
            ]
        )

        with SessionLocal() as session:
            service = RetrievalSearchService(
                session,
                embedding_provider=TestEmbeddingProvider(dimensions=8),
                vector_provider=vector_provider,
                rerank_provider=ReverseRerankProvider(),
            )
            results = service.search_meeting(
                workspace_id=self.workspace_id,
                meeting_id=meeting_id,
                query="risk action",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.chunk_id, "analysis.actionItems-001")
        self.assertEqual(service.last_rerank_metadata["provider"], "reverse-rerank")


def _chunk(
    chunk_id: str,
    section_type: str,
    text: str,
    provider: TestEmbeddingProvider,
    *,
    source_type: str = "structured",
    priority: int = 50,
) -> dict:
    embedding = provider.embed_text(text)
    return {
        "chunkId": chunk_id,
        "sourceType": source_type,
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
            "priority": priority,
            "embeddingProvider": embedding.provider_name,
            "embeddingModel": embedding.model_name,
        },
    }


if __name__ == "__main__":
    unittest.main()
