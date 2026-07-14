import unittest
from uuid import uuid4

from sqlalchemy import delete

from backend.configs.database import SessionLocal
from backend.models.core_models import User
from backend.models.enums import MeetingStatus
from backend.providers.analysis import ANALYSIS_CANDIDATE_SCHEMA_VERSION
from backend.providers.vector_provider import VectorProviderError, VectorSearchHit
from backend.providers.embedding_provider import EmbeddingProviderError
from backend.repositories.auth_repository import AuthRepository
from backend.repositories.meeting_repository import MeetingIntelligenceResultRepository, MeetingRepository
from backend.repositories.retrieval_repository import MeetingChunkRepository
from backend.services.retrieval.search_service import RetrievalSearchService
from backend.tests.fakes import TestEmbeddingProvider


class FakeVectorProvider:
    enabled = True
    provider_name = "fake-vector"

    def __init__(self, hits: list[VectorSearchHit]) -> None:
        self.hits = hits

    def upsert_chunks(self, chunks) -> dict:
        return {"provider": self.provider_name, "status": "upserted", "chunkCount": len(chunks)}

    def search_chunk_ids(self, *, meeting_id: str, query_vector: list[float], limit: int) -> list[VectorSearchHit]:
        return self.hits[:limit]


class BrokenVectorProvider:
    enabled = True
    provider_name = "broken-vector"

    def upsert_chunks(self, chunks) -> dict:
        raise VectorProviderError("vector unavailable")

    def search_chunk_ids(self, *, meeting_id: str, query_vector: list[float], limit: int) -> list[VectorSearchHit]:
        raise VectorProviderError("vector unavailable")


class BrokenEmbeddingProvider(TestEmbeddingProvider):
    provider_name = "broken-embedding"
    model_name = "broken-model"

    def embed_text(self, text: str):
        raise EmbeddingProviderError("embedding unavailable")


class ReverseRerankProvider:
    provider_name = "reverse-rerank"
    model_name = "test-rerank"

    def rerank(self, *, query: str, chunks: list, output_k: int) -> list:
        return list(reversed(chunks))[:output_k]


class RetrievalSearchServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.user_id = str(uuid4())
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
                schema_version=ANALYSIS_CANDIDATE_SCHEMA_VERSION,
                provider_name="test",
                provider_model="test",
                result_json={"schemaVersion": ANALYSIS_CANDIDATE_SCHEMA_VERSION},
            )
            provider = TestEmbeddingProvider(dimensions=8)
            summary_text = "The meeting covers processed JSON retrieval and chatbot evidence."
            topic_text = "Topic summary. title: Refund process. summary: The customer returned a coat because the size was wrong and the desired size was unavailable."
            timeline_summary_text = "Timeline summary. refund request, escalation, and follow-up deadline."
            fact_text = "Fact. type: participant_count. value: 2. unit: people. derived From: speakers."
            generic_fact_text = "Fact. type: refund_reason. value: The customer requires a refund for a returned coat because the size was wrong."
            citizenship_fact_text = "Fact. type: citizenship. value: Anthony is a United States citizen."
            event_text = "Event. type: customer_request. title: Customer requested refund support. status: completed."
            relationship_text = "Relationship. type: owns. from participant Bob. to action index action items."
            action_text = "Action item. owner Name: Bob. task: Bob must index action items by Friday. status: open."
            decision_text = "Decision. text: Use processed JSON for RAG. status: confirmed."
            risk_text = "Risk. text: Low quality audio may reduce answer confidence."
            participant_overview_text = "Participant overview. participant Count: 2. participants: Alice, Bob"
            participant_text = "Participant profile. display Name: Alice. role: Product owner. details: Alice led the meeting."
            meeting_text = "Meeting metadata. title: Retrieval search meeting. duration Seconds: 120"
            quality_text = "Quality overview. coverage: partial. confidence: 0.74"
            quality_warning_text = "Quality warning: low volume audio may reduce transcript confidence"
            source_text = "Processing source. analysis Provider: llm-analysis. analysis Model: test-analysis-model. llm Provider: test-llm"
            extraction_warning_text = "Extraction warning: No timeline evidence."
            entity_text = "Entity profile. type: term. name: RAG. definition: retrieval augmented generation."
            MeetingChunkRepository(session).replace_for_result(
                meeting_id=meeting.id,
                intelligence_result_id=result.id,
                chunks=[
                    _chunk("meeting-metadata", "meeting.metadata", meeting_text, provider, source_type="metadata", priority=5),
                    _chunk("source-processing", "source.processing", source_text, provider, source_type="metadata", priority=10),
                    _chunk("speaker-stats", "speaker.stats", fact_text, provider, priority=15),
                    _chunk("fact-participant_count-001", "fact.participant_count", fact_text, provider, priority=20),
                    _chunk("fact-record-001", "fact.record", generic_fact_text, provider, priority=30),
                    _chunk("fact-record-002", "fact.record", citizenship_fact_text, provider, priority=30),
                    _chunk("participant-overview", "participant.overview", participant_overview_text, provider, priority=35),
                    _chunk("participant-profile-001", "participant.profile", participant_text, provider, priority=40),
                    _chunk("action-item-001", "action.item", action_text, provider, priority=50),
                    _chunk("decision-record-001", "decision.record", decision_text, provider, priority=55),
                    _chunk("event-timeline-001", "event.timeline", event_text, provider, priority=60),
                    _chunk("relationship-edge-001", "relationship.edge", relationship_text, provider, priority=70),
                    _chunk("risk-record-001", "risk.record", risk_text, provider, priority=80),
                    _chunk("entity-profile-001", "entity.profile", entity_text, provider, priority=100),
                    _chunk("topic-summary-001", "topic.summary", topic_text, provider, priority=130),
                    _chunk("summary-executive", "summary.executive", summary_text, provider, priority=150),
                    _chunk("summary-topic-001", "summary.topic", topic_text, provider, priority=155),
                    _chunk("summary-timeline-001", "summary.timeline", timeline_summary_text, provider, priority=160),
                    _chunk("extraction-warning-001", "extraction.warning", extraction_warning_text, provider, source_type="metadata", priority=201),
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
                VectorSearchHit(chunk_id="risk-record-001", score=0.93),
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
                meeting_id=meeting_id,
                query="vector lookup smoke",
            )

        self.assertEqual([result.record.chunk_id for result in results], ["risk-record-001"])
        self.assertEqual(results[0].score, 0.93)

    def test_stale_vector_generation_is_rejected(self) -> None:
        meeting_id = self.create_meeting_chunks()
        vector_provider = FakeVectorProvider(
            [VectorSearchHit(chunk_id="risk-record-001", score=0.93, generation="stale-generation")]
        )

        with SessionLocal() as session:
            service = RetrievalSearchService(
                session,
                embedding_provider=TestEmbeddingProvider(dimensions=8),
                vector_provider=vector_provider,
            )
            results = service.search_meeting(
                meeting_id=meeting_id,
                query="vector lookup smoke",
            )

        self.assertEqual(results, [])

    def test_broken_vector_provider_falls_back_to_postgres_search(self) -> None:
        meeting_id = self.create_meeting_chunks()
        with SessionLocal() as session:
            service = RetrievalSearchService(
                session,
                embedding_provider=TestEmbeddingProvider(dimensions=8),
                vector_provider=BrokenVectorProvider(),
            )
            results = service.search_meeting(
                meeting_id=meeting_id,
                query="Who must index action items by Friday?",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.chunk_id, "action-item-001")

    def test_broken_embedding_provider_falls_back_to_postgres_search(self) -> None:
        meeting_id = self.create_meeting_chunks()
        with SessionLocal() as session:
            service = RetrievalSearchService(
                session,
                embedding_provider=BrokenEmbeddingProvider(dimensions=8),
                vector_provider=FakeVectorProvider([]),
            )
            results = service.search_meeting(
                meeting_id=meeting_id,
                query="Who must index action items by Friday?",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.chunk_id, "action-item-001")
        self.assertEqual(service.last_search_metadata["retrieval"]["provider"], "postgres-fallback-embedding")
        self.assertEqual(service.last_search_metadata["embedding"]["status"], "failed")

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
                meeting_id=meeting_id,
                query="Cuộc họp này bàn về vấn đề gì?",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.chunk_id, "summary-executive")
        self.assertEqual(results[1].record.chunk_id, "summary-topic-001")
        self.assertEqual(results[2].record.chunk_id, "topic-summary-001")
        self.assertEqual(service.last_rerank_metadata["intentPinnedCount"], 4)

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
                meeting_id=meeting_id,
                query="Cuộc gọi này có bao nhiêu người tham gia?",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.chunk_id, "fact-participant_count-001")
        self.assertEqual(results[1].record.chunk_id, "speaker-stats")
        self.assertEqual(results[2].record.chunk_id, "participant-overview")
        self.assertEqual(service.last_rerank_metadata["intentPinnedCount"], 5)

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
                meeting_id=meeting_id,
                query="Phần nào thiếu bằng chứng?",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.chunk_id, "extraction-warning-001")

    def test_vietnamese_nationality_question_pins_fact_chunks(self) -> None:
        meeting_id = self.create_meeting_chunks()
        with SessionLocal() as session:
            service = RetrievalSearchService(
                session,
                embedding_provider=TestEmbeddingProvider(dimensions=8),
                vector_provider=BrokenVectorProvider(),
                rerank_provider=ReverseRerankProvider(),
            )
            results = service.search_meeting(
                meeting_id=meeting_id,
                query="Quốc tịch của họ là gì?",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.section_type, "fact.record")
        self.assertEqual(results[0].record.chunk_id, "fact-record-002")
        self.assertEqual(service.last_rerank_metadata["intentPinnedCount"], 4)

    def test_vietnamese_participant_nationality_question_prefers_fact_over_participant_intent(self) -> None:
        meeting_id = self.create_meeting_chunks()
        with SessionLocal() as session:
            service = RetrievalSearchService(
                session,
                embedding_provider=TestEmbeddingProvider(dimensions=8),
                vector_provider=BrokenVectorProvider(),
                rerank_provider=ReverseRerankProvider(),
            )
            results = service.search_meeting(
                meeting_id=meeting_id,
                query="Những người tham gia cuộc họp có quốc tịch là gì?",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.section_type, "fact.record")
        self.assertEqual(results[0].record.chunk_id, "fact-record-002")

    def test_vietnamese_nationality_confirmation_question_pins_fact_chunks(self) -> None:
        meeting_id = self.create_meeting_chunks()
        with SessionLocal() as session:
            service = RetrievalSearchService(
                session,
                embedding_provider=TestEmbeddingProvider(dimensions=8),
                vector_provider=BrokenVectorProvider(),
                rerank_provider=ReverseRerankProvider(),
            )
            results = service.search_meeting(
                meeting_id=meeting_id,
                query="Quốc tịch của họ là Mỹ đúng không?",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.section_type, "fact.record")
        self.assertEqual(results[0].record.chunk_id, "fact-record-002")

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
                meeting_id=meeting_id,
                query="Tại sao khách lại muốn đổi trả áo?",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.chunk_id, "event-timeline-001")
        self.assertEqual(results[1].record.chunk_id, "relationship-edge-001")
        self.assertEqual(results[2].record.chunk_id, "fact-record-001")
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
                meeting_id=meeting_id,
                query="Khách có thể đổi trả hàng như nào?",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.chunk_id, "event-timeline-001")
        self.assertEqual(results[1].record.chunk_id, "action-item-001")
        self.assertEqual(results[2].record.chunk_id, "decision-record-001")
        self.assertEqual(service.last_rerank_metadata["intentPinnedCount"], 6)

    def test_rerank_provider_reorders_vector_candidates(self) -> None:
        meeting_id = self.create_meeting_chunks()
        vector_provider = FakeVectorProvider(
            [
                VectorSearchHit(chunk_id="risk-record-001", score=0.99),
                VectorSearchHit(chunk_id="action-item-001", score=0.91),
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
                meeting_id=meeting_id,
                query="risk action",
            )

        self.assertTrue(results)
        self.assertEqual(results[0].record.chunk_id, "action-item-001")
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
        "jsonPointer": f"/{section_type.split('.')[0]}/0",
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
