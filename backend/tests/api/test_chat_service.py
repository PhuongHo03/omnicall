import unittest
from uuid import uuid4

from sqlalchemy import delete

from backend.configs.database import SessionLocal
from backend.dependencies.auth import CurrentUserContext
from backend.dtos.meeting_dto import MeetingChatRequest
from backend.models.core_models import User
from backend.models.enums import MeetingStatus
from backend.providers.analysis import ANALYSIS_CANDIDATE_SCHEMA_VERSION
from backend.repositories.auth_repository import AuthRepository
from backend.repositories.chat_repository import ChatMessageRepository
from backend.repositories.meeting_repository import (
    MeetingIntelligenceResultRepository,
    MeetingRepository,
)
from backend.repositories.retrieval_repository import MeetingChunkRepository
from backend.services.agent.service import AgentResult
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


class FakeParticipantLLMProvider:
    provider_name = "fake-chat-llm"
    model_name = "fake-chat-model"

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        return {
            "answer": "Cuộc gọi có 2 người tham gia: Alice và Bob.",
            "evidenceState": "grounded",
            "confidence": 0.93,
        }


class FakeAgenticRAGService:
    def __init__(self, answer: str, chunks: list[dict], evidence_state: str = "grounded") -> None:
        self.answer = answer
        self.chunks = chunks
        self.evidence_state = evidence_state
        self.calls: list[dict] = []

    def generate_answer(self, *, meeting_id: str, question: str, event_callback=None) -> AgentResult:
        self.calls.append({"meeting_id": meeting_id, "question": question})
        if event_callback:
            event_callback({"type": "agent_synthesize", "message": "Đang tạo câu trả lời cuối cùng..."})
        return AgentResult(
            answer=self.answer,
            evidence_state=self.evidence_state,
            confidence=0.91,
            provider="fake-agent",
            model="fake-agent-model",
            iterations=1,
            total_duration_ms=12,
            tool_calls_summary=[{"tool": "search_semantic", "success": True}],
            agent_thoughts=[{"iteration": 1, "thought": "Use retrieved meeting chunks."}],
            metadata={"chunks": self.chunks, "tokenUsage": {"total": 42}},
        )


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

    def test_generate_answer_saves_history_directly_by_meeting(self) -> None:
        meeting_id, chunks = self._create_ready_meeting_with_chunk()
        with SessionLocal() as session:
            user_message = ChatMessageRepository(session).create(
                meeting_id=meeting_id,
                role="user",
                content="Who must index action items by Friday?",
            )
            session.commit()
            service = MeetingChatService(
                session,
                llm_provider=FakeChatLLMProvider(),
                guardrail_provider=TestGuardrailProvider(),
                agentic_rag_service=FakeAgenticRAGService(
                    "Bob cần index action items trước thứ Sáu.",
                    [chunks["action"]],
                ),
            )

            response = service.generate_answer(
                meeting_id=meeting_id,
                user_id=self.user_id,
                question="Who must index action items by Friday?",
                user_message_id=user_message.id,
                input_guardrails={},
            )
            history = service.get_history(self.context, meeting_id)

        self.assertEqual(response["status"], "succeeded")
        self.assertEqual(len(history.messages), 2)
        self.assertEqual([message.role for message in history.messages], ["user", "assistant"])
        self.assertEqual(history.messages[1].retrieved_chunk_ids, ["action-item-001"])
        self.assertEqual(history.messages[1].citations[0].chunk_id, "action-item-001")
        self.assertEqual(history.messages[1].citations[0].citation_id, "cite-001")
        self.assertIn("Bob must index", history.messages[1].citations[0].quote)
        self.assertEqual(history.messages[1].metadata["agentIterations"], 1)

    def test_error_response_is_idempotent_per_user_message(self) -> None:
        meeting_id, _ = self._create_ready_meeting_with_chunk()
        with SessionLocal() as session:
            user_message = ChatMessageRepository(session).create(
                meeting_id=meeting_id,
                role="user",
                content="Temporary failure test",
            )
            session.commit()
            service = MeetingChatService(session)
            service.save_error_response(meeting_id=meeting_id, user_message_id=user_message.id)
            service.save_error_response(meeting_id=meeting_id, user_message_id=user_message.id)
            history = service.get_history(self.context, meeting_id)

        self.assertEqual(len(history.messages), 2)
        self.assertEqual(history.messages[1].metadata["evidenceState"], "error")

    def test_generate_answer_does_not_promote_uncited_structured_chunks(self) -> None:
        meeting_id, chunks = self._create_ready_meeting_with_chunk()
        with SessionLocal() as session:
            user_message = ChatMessageRepository(session).create(
                meeting_id=meeting_id,
                role="user",
                content="Cuộc gọi này có bao nhiêu người tham gia?",
            )
            session.commit()
            service = MeetingChatService(
                session,
                llm_provider=FakeParticipantLLMProvider(),
                guardrail_provider=TestGuardrailProvider(),
                agentic_rag_service=FakeAgenticRAGService(
                    "Cuộc gọi có 2 người tham gia: Alice và Bob.",
                    [chunks["participants"]],
                ),
            )

            response = service.generate_answer(
                meeting_id=meeting_id,
                user_id=self.user_id,
                question="Cuộc gọi này có bao nhiêu người tham gia?",
                user_message_id=user_message.id,
                input_guardrails={},
            )
            history = service.get_history(self.context, meeting_id)

        self.assertEqual(response["status"], "succeeded")
        self.assertEqual(history.messages[1].citations, [])

    def test_ask_queues_chat_generation_and_marks_pending(self) -> None:
        meeting_id, _ = self._create_ready_meeting_with_chunk()
        delayed_calls = []

        with SessionLocal() as session:
            service = MeetingChatService(session, guardrail_provider=TestGuardrailProvider())

            from unittest.mock import patch

            with patch("backend.tasks.chat_tasks.generate_chat_answer.delay", lambda **kwargs: delayed_calls.append(kwargs)):
                response = service.ask(
                    self.context,
                    meeting_id,
                    MeetingChatRequest(question="Who must index action items by Friday?"),
                )
            meeting = MeetingRepository(session).get(meeting_id)
            messages = ChatMessageRepository(session).list_for_meeting(meeting_id=meeting_id)

        self.assertEqual(response.status, "processing")
        self.assertEqual(meeting.pending_chat_status, "queued")
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].role, "user")
        self.assertEqual(delayed_calls[0]["meeting_id"], meeting_id)

    def test_chat_message_repository_has_no_chat_session_layer(self) -> None:
        meeting_id, _ = self._create_ready_meeting_with_chunk()
        with SessionLocal() as session:
            repository = ChatMessageRepository(session)
            repository.create(meeting_id=meeting_id, role="user", content="Question?")
            repository.create(meeting_id=meeting_id, role="assistant", content="Answer.")
            session.commit()

            messages = repository.list_for_meeting(meeting_id=meeting_id)

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].meeting_id, meeting_id)
        self.assertEqual(messages[1].meeting_id, meeting_id)

    def _create_ready_meeting_with_chunk(self) -> tuple[str, dict[str, dict]]:
        with SessionLocal() as session:
            meeting_repo = MeetingRepository(session)
            result_repo = MeetingIntelligenceResultRepository(session)
            meeting = meeting_repo.create(
                user_id=self.user_id,
                title="Chat service meeting",
            )
            meeting_repo.update_status(meeting, MeetingStatus.READY)
            result = result_repo.upsert(
                meeting_id=meeting.id,
                schema_version=ANALYSIS_CANDIDATE_SCHEMA_VERSION,
                provider_name="test",
                provider_model="test",
                result_json={"schemaVersion": ANALYSIS_CANDIDATE_SCHEMA_VERSION},
            )
            text = "Bob must index action items and risks by Friday."
            embedding_provider = TestEmbeddingProvider(dimensions=8)
            embedding = embedding_provider.embed_text(text)
            participant_overview_text = "Participant overview. participant Count: 2. participants: Alice, Bob"
            participant_text = "Participant profile. display Name: Alice. role: Product owner. details: Alice led the meeting."
            participant_chunk = {
                "chunkId": "participant-overview",
                "sourceType": "structured",
                "sectionType": "participant.overview",
                "jsonPointer": "/participants",
                "text": participant_overview_text,
                "citationIds": [],
                "segmentIds": [],
                "startMs": None,
                "endMs": None,
            }
            action_chunk = {
                "chunkId": "action-item-001",
                "sourceType": "structured",
                "sectionType": "action.item",
                "jsonPointer": "/actions/0",
                "text": text,
                "citationIds": ["cite-001"],
                "segmentIds": ["seg-001"],
                "startMs": 1000,
                "endMs": 5000,
            }
            MeetingChunkRepository(session).replace_for_result(
                meeting_id=meeting.id,
                intelligence_result_id=result.id,
                chunks=[
                    {
                        "chunkId": "participant-overview",
                        "sourceType": "structured",
                        "sectionType": "participant.overview",
                        "sourceId": "participant-overview",
                        "jsonPointer": "/participants",
                        "text": participant_overview_text,
                        "citationIds": [],
                        "segmentIds": [],
                        "startMs": None,
                        "endMs": None,
                        "tokenCount": 8,
                        "embedding": embedding_provider.embed_text(participant_overview_text).vector,
                        "visibility": "owner",
                        "metadata": {
                            "priority": 35,
                            "embeddingProvider": embedding.provider_name,
                            "embeddingModel": embedding.model_name,
                        },
                    },
                    {
                        "chunkId": "participant-profile-001",
                        "sourceType": "structured",
                        "sectionType": "participant.profile",
                        "sourceId": "Alice",
                        "jsonPointer": "/participants/0",
                        "text": participant_text,
                        "citationIds": ["cite-001"],
                        "segmentIds": ["seg-001"],
                        "startMs": 1000,
                        "endMs": 5000,
                        "tokenCount": 9,
                        "embedding": embedding_provider.embed_text(participant_text).vector,
                        "visibility": "owner",
                        "metadata": {
                            "priority": 40,
                            "embeddingProvider": embedding.provider_name,
                            "embeddingModel": embedding.model_name,
                        },
                    },
                    {
                        "chunkId": "action-item-001",
                        "sourceType": "structured",
                        "sectionType": "action.item",
                        "sourceId": "action-001",
                        "jsonPointer": "/actions/0",
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
            return meeting.id, {"participants": participant_chunk, "action": action_chunk}


if __name__ == "__main__":
    unittest.main()
