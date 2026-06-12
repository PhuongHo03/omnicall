import unittest
from uuid import uuid4

from sqlalchemy import delete

from backend.configs.database import SessionLocal
from backend.dependencies.auth import CurrentUserContext
from backend.dtos.meeting_dto import MeetingChatRequest
from backend.models.core_models import User, Workspace
from backend.models.enums import MeetingStatus, ProcessingJobStatus
from backend.providers.analysis_provider import SCHEMA_VERSION
from backend.providers.embedding_provider import LocalHashEmbeddingProvider
from backend.providers.llm_provider import LLMProviderError
from backend.providers.vector_provider import NoopVectorProvider
from backend.repositories.auth_repository import AuthRepository
from backend.repositories.meeting_repository import MeetingIntelligenceResultRepository, MeetingRepository, ProcessingJobRepository
from backend.repositories.retrieval_repository import MeetingChunkRepository
from backend.services.chat_service import MeetingChatService
from backend.services.retrieval_search_service import RetrievalSearchService
from backend.utils.exceptions import ApplicationError


class FakeChatLLMProvider:
    provider_name = "fake-chat-llm"
    model_name = "fake-chat-model"

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        return {
            "answer": "Bob cần index action items trước thứ Sáu.",
            "evidenceState": "grounded",
            "confidence": 0.91,
        }


class BrokenChatLLMProvider:
    provider_name = "broken-chat-llm"
    model_name = "broken-chat-model"

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        raise LLMProviderError("chat provider unavailable")


class ChatServiceTestCase(unittest.TestCase):
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
                display_name="Chat Test User",
                workspace_name="Chat Test Workspace",
            )
            session.commit()

    def tearDown(self) -> None:
        with SessionLocal() as session:
            session.execute(delete(Workspace).where(Workspace.id == self.workspace_id))
            session.execute(delete(User).where(User.id == self.user_id))
            session.commit()

    def create_ready_meeting(self, *, with_chunks: bool) -> str:
        with SessionLocal() as session:
            meeting_repo = MeetingRepository(session)
            job_repo = ProcessingJobRepository(session)
            result_repo = MeetingIntelligenceResultRepository(session)
            meeting = meeting_repo.create(
                workspace_id=self.workspace_id,
                user_id=self.user_id,
                title="Chat service meeting",
                language="vi",
            )
            meeting_repo.update_status(meeting, MeetingStatus.READY)
            job = job_repo.create(
                workspace_id=self.workspace_id,
                meeting_id=meeting.id,
                idempotency_key=f"chat-test-{uuid4()}",
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
            if with_chunks:
                provider = LocalHashEmbeddingProvider(dimensions=8)
                text = "Bob must index action items and risks by Friday."
                embedding = provider.embed_text(text)
                MeetingChunkRepository(session).replace_for_result(
                    workspace_id=self.workspace_id,
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
                            "visibility": "workspace",
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

    def test_chat_saves_messages_and_citations(self) -> None:
        meeting_id = self.create_ready_meeting(with_chunks=True)
        with SessionLocal() as session:
            service = self.make_service(session, FakeChatLLMProvider())

            response = service.ask(
                self.context,
                meeting_id,
                MeetingChatRequest(question="Who must index action items by Friday?"),
            )
            history = service.get_history(self.context, meeting_id, response.session_id)

        self.assertEqual(response.evidence_state, "grounded")
        self.assertEqual(response.citations[0].chunk_id, "analysis.actionItems-001")
        self.assertEqual(response.citations[0].segment_ids, ["seg-001"])
        self.assertEqual(len(history.messages), 2)
        self.assertEqual(history.messages[0].role, "user")
        self.assertEqual(history.messages[1].role, "assistant")
        self.assertEqual(history.messages[1].retrieved_chunk_ids, ["analysis.actionItems-001"])

    def test_chat_returns_not_enough_evidence_without_chunks(self) -> None:
        meeting_id = self.create_ready_meeting(with_chunks=False)
        with SessionLocal() as session:
            service = self.make_service(session, FakeChatLLMProvider())

            response = service.ask(
                self.context,
                meeting_id,
                MeetingChatRequest(question="What was the budget decision?"),
            )

        self.assertEqual(response.evidence_state, "not_enough_evidence")
        self.assertEqual(response.citations, [])
        self.assertIn("Không đủ bằng chứng", response.answer)

    def test_chat_falls_back_to_local_retrieval_summary_when_llm_fails(self) -> None:
        meeting_id = self.create_ready_meeting(with_chunks=True)
        with SessionLocal() as session:
            service = self.make_service(session, BrokenChatLLMProvider())

            response = service.ask(
                self.context,
                meeting_id,
                MeetingChatRequest(question="Who must index action items by Friday?"),
            )

        self.assertEqual(response.evidence_state, "partial")
        self.assertIn("Dựa trên dữ liệu cuộc họp", response.answer)
        self.assertEqual(response.message.metadata["provider"], "local-retrieval-summary")

    def test_chat_history_is_scoped_to_workspace(self) -> None:
        meeting_id = self.create_ready_meeting(with_chunks=True)
        with SessionLocal() as session:
            service = self.make_service(session, FakeChatLLMProvider())
            response = service.ask(
                self.context,
                meeting_id,
                MeetingChatRequest(question="Who must index action items by Friday?"),
            )
            other_context = CurrentUserContext(
                user_id=str(uuid4()),
                workspace_id=str(uuid4()),
                role="owner",
            )

            with self.assertRaises(ApplicationError) as error:
                service.get_history(other_context, meeting_id, response.session_id)

        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(error.exception.code, "meeting_not_found")

    @staticmethod
    def make_service(session, llm_provider) -> MeetingChatService:
        return MeetingChatService(
            session,
            llm_provider=llm_provider,
            retrieval_search=RetrievalSearchService(
                session,
                embedding_provider=LocalHashEmbeddingProvider(dimensions=8),
                vector_provider=NoopVectorProvider(),
            ),
        )


if __name__ == "__main__":
    unittest.main()
