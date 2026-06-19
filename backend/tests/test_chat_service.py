import unittest
from uuid import uuid4

from sqlalchemy import delete

from backend.configs.database import SessionLocal
from backend.dependencies.auth import CurrentUserContext
from backend.dtos.meeting_dto import MeetingChatRequest
from backend.models.core_models import User
from backend.models.enums import MeetingStatus, ProcessingJobStatus
from backend.providers.analysis_provider import SCHEMA_VERSION
from backend.providers.vector_provider import VectorProviderError
from backend.repositories.auth_repository import AuthRepository
from backend.repositories.chat_repository import ChatMessageRepository
from backend.repositories.meeting_repository import (
    MeetingIntelligenceResultRepository,
    MeetingRepository,
    ProcessingJobRepository,
)
from backend.repositories.retrieval_repository import MeetingChunkRepository
from backend.services.chat_service import MeetingChatService
from backend.tests.fakes import TestEmbeddingProvider, TestGuardrailProvider


class FakeChatLLMProvider:
    provider_name = "fake-chat-llm"
    model_name = "fake-chat-model"

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        return {
            "answer": "Bob cần index action items trước thứ Sáu.",
            "evidenceState": "grounded",
            "confidence": 0.91,
        }


class BrokenVectorProvider:
    enabled = True
    provider_name = "broken-vector"

    def upsert_chunks(self, chunks) -> dict:
        raise VectorProviderError("vector unavailable")

    def search_chunk_ids(self, *, workspace_id: str, meeting_id: str, query_vector: list[float], limit: int):
        raise VectorProviderError("vector unavailable")


class IdentityRerankProvider:
    provider_name = "identity-rerank"
    model_name = "test-rerank"

    def rerank(self, *, query: str, chunks: list, output_k: int) -> list:
        return chunks[:output_k]


class ChatServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.user_id = str(uuid4())
        self.context = CurrentUserContext(user_id=self.user_id, role="User")
        with SessionLocal() as session:
            AuthRepository(session).upsert_dev_user(
                user_id=self.user_id,
                email=f"{self.user_id}@test.omnicall",
                display_name="Chat Test User",
                role="User",
            )
            session.commit()

    def tearDown(self) -> None:
        with SessionLocal() as session:
            session.execute(delete(User).where(User.id == self.user_id))
            session.commit()

    def test_chat_saves_history_directly_by_meeting(self) -> None:
        meeting_id = self._create_ready_meeting_with_chunk()
        with SessionLocal() as session:
            service = MeetingChatService(
                session,
                llm_provider=FakeChatLLMProvider(),
                guardrail_provider=TestGuardrailProvider(),
            )
            service.retrieval_search.vector_provider = BrokenVectorProvider()
            service.retrieval_search.embedding_provider = TestEmbeddingProvider(dimensions=8)
            service.retrieval_search.rerank_provider = IdentityRerankProvider()

            response = service.ask(
                self.context,
                meeting_id,
                MeetingChatRequest(question="Who must index action items by Friday?"),
            )
            history = service.get_history(self.context, meeting_id)

        self.assertEqual(response.evidence_state, "grounded")
        self.assertEqual(response.citations[0].chunk_id, "analysis.actionItems-001")
        self.assertEqual(len(history.messages), 2)
        self.assertEqual([message.role for message in history.messages], ["user", "assistant"])
        self.assertEqual(history.messages[1].retrieved_chunk_ids, ["analysis.actionItems-001"])

    def test_chat_message_repository_has_no_chat_session_layer(self) -> None:
        meeting_id = self._create_ready_meeting_with_chunk()
        with SessionLocal() as session:
            repository = ChatMessageRepository(session)
            repository.create(meeting_id=meeting_id, role="user", content="Question?")
            repository.create(meeting_id=meeting_id, role="assistant", content="Answer.")
            session.commit()

            messages = repository.list_for_meeting(meeting_id=meeting_id)

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].meeting_id, meeting_id)
        self.assertEqual(messages[1].meeting_id, meeting_id)

    def _create_ready_meeting_with_chunk(self) -> str:
        with SessionLocal() as session:
            meeting_repo = MeetingRepository(session)
            job_repo = ProcessingJobRepository(session)
            result_repo = MeetingIntelligenceResultRepository(session)
            meeting = meeting_repo.create(
                user_id=self.user_id,
                title="Chat service meeting",
                language="vi",
            )
            meeting_repo.update_status(meeting, MeetingStatus.READY)
            job = job_repo.create(
                meeting_id=meeting.id,
                idempotency_key=f"chat-test-{uuid4()}",
                payload={"meetingId": meeting.id},
                status=ProcessingJobStatus.SUCCEEDED,
            )
            result = result_repo.upsert(
                meeting_id=meeting.id,
                processing_job_id=job.id,
                schema_version=SCHEMA_VERSION,
                provider_name="test",
                provider_model="test",
                result_json={"schemaVersion": SCHEMA_VERSION},
            )
            text = "Bob must index action items and risks by Friday."
            embedding = TestEmbeddingProvider(dimensions=8).embed_text(text)
            MeetingChunkRepository(session).replace_for_result(
                meeting_id=meeting.id,
                intelligence_result_id=result.id,
                chunks=[
                    {
                        "chunkId": "analysis.actionItems-001",
                        "sourceType": "structured",
                        "sectionType": "analysis.actionItems",
                        "sourceId": "action-001",
                        "jsonPointer": "/analysis/actionItems/0",
                        "text": text,
                        "citationIds": ["cite-001"],
                        "segmentIds": ["seg-001"],
                        "startMs": 1000,
                        "endMs": 5000,
                        "tokenCount": 9,
                        "embedding": embedding.vector,
                        "visibility": "owner",
                        "metadata": {
                            "priority": 50,
                            "embeddingProvider": embedding.provider_name,
                            "embeddingModel": embedding.model_name,
                        },
                    }
                ],
            )
            session.commit()
            return meeting.id


if __name__ == "__main__":
    unittest.main()
