import unittest
from types import SimpleNamespace

from backend.services.admin_operational_log_service import AdminOperationalLogService


class FakeOperationalLogs:
    def __init__(self, events: list[dict]) -> None:
        self.events = events

    def tail(self, **_: object) -> list[dict]:
        return self.events


class FakeTurns:
    def __init__(self, turns: list[object]) -> None:
        self.turns = turns

    def list_by_ids(self, turn_ids: list[str]) -> list[object]:
        return [turn for turn in self.turns if turn.id in turn_ids]


class FakeMessages:
    def __init__(self, messages: list[object]) -> None:
        self.messages = messages

    def list_by_ids(self, message_ids: list[str]) -> list[object]:
        return [message for message in self.messages if message.id in message_ids]


class AdminOperationalLogServiceTestCase(unittest.TestCase):
    def test_tail_hydrates_full_chat_from_turn_id_without_mutating_stored_event(self) -> None:
        event = {
            "id": "1-0",
            "flow": "rag",
            "stage": "answer",
            "status": "succeeded",
            "meetingId": "meeting-1",
            "chat": {"turnId": "turn-1", "questionPreview": "Short question"},
            "details": {},
        }
        turn = SimpleNamespace(
            id="turn-1",
            meeting_id="meeting-1",
            user_message_id="user-1",
            assistant_message_id="assistant-1",
        )
        messages = [
            SimpleNamespace(id="user-1", role="user", content="Full question"),
            SimpleNamespace(id="assistant-1", role="assistant", content="Full answer"),
        ]
        service = AdminOperationalLogService(
            None,  # type: ignore[arg-type]
            FakeOperationalLogs([event]),  # type: ignore[arg-type]
            chat_messages=FakeMessages(messages),  # type: ignore[arg-type]
            chat_turns=FakeTurns([turn]),  # type: ignore[arg-type]
        )

        result = service.tail(limit=10)

        self.assertEqual(result[0]["chat"]["question"], "Full question")
        self.assertEqual(result[0]["chat"]["answer"], "Full answer")
        self.assertEqual(result[0]["chat"]["assistantMessageId"], "assistant-1")
        self.assertNotIn("question", event["chat"])

    def test_queued_event_never_receives_a_later_terminal_answer(self) -> None:
        event = {
            "id": "queued-1",
            "flow": "rag",
            "stage": "question",
            "status": "queued",
            "meetingId": "meeting-1",
            "chat": {"turnId": "turn-1"},
            "details": {},
        }
        turn = SimpleNamespace(
            id="turn-1",
            meeting_id="meeting-1",
            user_message_id="user-1",
            assistant_message_id="assistant-1",
        )
        messages = [
            SimpleNamespace(id="user-1", role="user", content="Full question"),
            SimpleNamespace(id="assistant-1", role="assistant", content="Later answer"),
        ]
        service = AdminOperationalLogService(
            None,  # type: ignore[arg-type]
            FakeOperationalLogs([event]),  # type: ignore[arg-type]
            chat_messages=FakeMessages(messages),  # type: ignore[arg-type]
            chat_turns=FakeTurns([turn]),  # type: ignore[arg-type]
        )

        result = service.tail(limit=10)

        self.assertEqual(result[0]["chat"]["question"], "Full question")
        self.assertNotIn("assistantMessageId", result[0]["chat"])
        self.assertNotIn("answer", result[0]["chat"])

    def test_tail_accepts_legacy_turn_id_from_details(self) -> None:
        event = {
            "id": "2-0",
            "meetingId": "meeting-1",
            "chat": {},
            "details": {"turnId": "turn-1"},
        }
        turn = SimpleNamespace(
            id="turn-1",
            meeting_id="meeting-1",
            user_message_id="user-1",
            assistant_message_id=None,
        )
        message = SimpleNamespace(id="user-1", role="user", content="Persisted question")
        service = AdminOperationalLogService(
            None,  # type: ignore[arg-type]
            FakeOperationalLogs([event]),  # type: ignore[arg-type]
            chat_messages=FakeMessages([message]),  # type: ignore[arg-type]
            chat_turns=FakeTurns([turn]),  # type: ignore[arg-type]
        )

        result = service.tail(limit=10)

        self.assertEqual(result[0]["chat"]["turnId"], "turn-1")
        self.assertEqual(result[0]["chat"]["question"], "Persisted question")


if __name__ == "__main__":
    unittest.main()
