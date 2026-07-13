import unittest

from backend.providers.transcript_types import TranscriptSegment
from backend.services.processing.transcript_window_service import TranscriptWindowService


class TranscriptWindowServiceTestCase(unittest.TestCase):
    def test_windows_are_bounded_and_overlap_previous_turn(self) -> None:
        segments = [
            TranscriptSegment("seg-001", "A", 0, 1000, "A" * 120, 0.9),
            TranscriptSegment("seg-002", "B", 1000, 2000, "B" * 120, 0.9),
            TranscriptSegment("seg-003", "C", 2000, 3000, "C" * 120, 0.9),
        ]
        windows = TranscriptWindowService(target_tokens=70, hard_limit_tokens=90, overlap_segments=1).build(segments)

        self.assertGreater(len(windows), 1)
        self.assertEqual(windows[0].segments[-1].id, windows[1].segments[0].id)
        self.assertEqual([item.sequence_no for item in windows], list(range(1, len(windows) + 1)))
        self.assertEqual(windows[0].start_ms, 0)
        self.assertGreater(windows[-1].end_ms, windows[0].end_ms)


if __name__ == "__main__":
    unittest.main()
