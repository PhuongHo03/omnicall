import unittest
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

from backend.tasks.processing_tasks import process_meeting


class RetryRequested(RuntimeError):
    pass


class ProcessingTaskTestCase(unittest.TestCase):
    def test_lock_lost_result_is_retried(self) -> None:
        service = MagicMock()
        service.process_meeting.return_value = {
            "meeting_id": "meeting-1",
            "status": "lock_lost",
        }
        with (
            patch("backend.tasks.processing_tasks.SessionLocal", return_value=nullcontext(MagicMock())),
            patch("backend.tasks.processing_tasks.ProcessingPipelineService", return_value=service),
            patch.object(process_meeting, "retry", side_effect=RetryRequested) as retry,
        ):
            with self.assertRaises(RetryRequested):
                process_meeting.run(meeting_id="meeting-1")

        retry.assert_called_once()

    def test_successful_result_is_returned_without_retry(self) -> None:
        expected = {"meeting_id": "meeting-1", "status": "succeeded"}
        service = MagicMock()
        service.process_meeting.return_value = expected
        with (
            patch("backend.tasks.processing_tasks.SessionLocal", return_value=nullcontext(MagicMock())),
            patch("backend.tasks.processing_tasks.ProcessingPipelineService", return_value=service),
            patch.object(process_meeting, "retry") as retry,
        ):
            result = process_meeting.run(meeting_id="meeting-1")

        self.assertEqual(result, expected)
        retry.assert_not_called()


if __name__ == "__main__":
    unittest.main()
