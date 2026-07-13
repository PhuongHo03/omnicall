import unittest

from backend.configs.settings import Settings
from backend.services.operational_log_service import OperationalLogService


class FakeOperationalLogProvider:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.clear_calls = 0

    def append(self, event: dict) -> str:
        event_id = f"{len(self.events) + 1}-0"
        self.events.insert(0, {"id": event_id, **event})
        return event_id

    def tail(self, limit: int) -> list[dict]:
        return self.events[:limit]

    def clear(self) -> int:
        self.clear_calls += 1
        had_events = bool(self.events)
        self.events.clear()
        return int(had_events)

    def delete_events(self, event_ids: list[str]) -> int:
        event_ids_set = set(event_ids)
        before = len(self.events)
        self.events = [event for event in self.events if event["id"] not in event_ids_set]
        return before - len(self.events)


class OperationalLogServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = FakeOperationalLogProvider()
        self.service = OperationalLogService(
            provider=self.provider,
            settings=Settings(OPERATIONAL_LOG_MAX_LENGTH=1000),
        )

    def test_emit_tail_filter_and_clear(self) -> None:
        self.service.emit(
            level="info",
            flow="processing",
            stage="asr",
            status="succeeded",
            message="ASR completed.",
            meeting_name="Session A",
            file={"name": "meeting.mp3"},
            provider="local-asr",
            model="whisper-medium",
        )
        self.service.emit(
            level="error",
            flow="rag",
            stage="rerank",
            status="failed",
            message="Rerank failed.",
            meeting_name="Session B",
            provider="local-rerank",
            model="bge-reranker",
        )

        processing = self.service.tail(limit=100, flow="processing")
        errors = self.service.tail(limit=100, level="error")
        searched = self.service.tail(limit=100, search="meeting.mp3")

        self.assertEqual([event["stage"] for event in processing], ["asr"])
        self.assertEqual([event["stage"] for event in errors], ["rerank"])
        self.assertEqual([event["meetingName"] for event in searched], ["Session A"])
        self.assertEqual(self.service.clear(), 1)
        self.assertEqual(self.service.tail(limit=100), [])

    def test_emit_redacts_secrets_but_keeps_operational_counts(self) -> None:
        self.service.emit(
            level="info",
            flow="rag",
            stage="answer_llm",
            status="succeeded",
            message="Answer generated.",
            details={
                "apiKey": "secret-value",
                "systemPrompt": "hidden prompt",
                "tokenCount": 123,
                "questionPreview": "What was decided?",
            },
        )

        event = self.service.tail(limit=1)[0]
        self.assertEqual(event["details"]["apiKey"], "[redacted]")
        self.assertEqual(event["details"]["systemPrompt"], "[redacted]")
        self.assertEqual(event["details"]["tokenCount"], 123)
        self.assertEqual(event["details"]["questionPreview"], "What was decided?")

    def test_unknown_levels_are_not_written(self) -> None:
        self.service.emit(
            level="debug",
            flow="processing",
            stage="asr",
            status="started",
            message="Ignored.",
        )

        self.assertEqual(self.provider.events, [])

    def test_clear_by_meeting_removes_only_matching_events(self) -> None:
        for meeting_id in ("meeting-a", "meeting-b"):
            self.service.emit(
                level="info",
                flow="processing",
                stage="file",
                status="succeeded",
                message="Uploaded.",
                meeting_id=meeting_id,
            )

        self.assertEqual(self.service.clear_by_meeting("meeting-a"), 1)
        self.assertEqual([event["meetingId"] for event in self.service.tail(limit=100)], ["meeting-b"])


if __name__ == "__main__":
    unittest.main()
