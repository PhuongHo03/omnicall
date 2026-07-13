import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.providers.transcript_types import TranscriptSegment
from backend.providers.voice import (
    _best_turn as voice_best_turn,
    _segment_with_speaker,
    _merge_diarization_payload,
)
from backend.model_runners.diarization import (
    _best_turn as runner_best_turn,
    _assign_segments,
    _dynamic_confidence,
    _min_overlap_threshold,
)


class TestVoiceProviderMatching(unittest.TestCase):
    """Test overlap ratio matching in voice_provider.py"""

    def _segment(self, start_ms: int, end_ms: int) -> TranscriptSegment:
        return TranscriptSegment(
            id="seg-001", speaker="unknown", start_ms=start_ms, end_ms=end_ms,
            text="hello", confidence=0.8,
        )

    def test_best_turn_returns_tuple_with_overlap_ratio(self) -> None:
        segment = self._segment(0, 1000)
        turns = [{"speaker": "Speaker 1", "startMs": 0, "endMs": 1000, "confidence": 0.9}]
        turn, ratio = voice_best_turn(segment, turns)
        self.assertEqual(turn["speaker"], "Speaker 1")
        self.assertAlmostEqual(ratio, 1.0, places=2)

    def test_best_turn_partial_overlap_returns_ratio(self) -> None:
        segment = self._segment(0, 1000)
        turns = [{"speaker": "Speaker 1", "startMs": 500, "endMs": 1500, "confidence": 0.9}]
        turn, ratio = voice_best_turn(segment, turns)
        self.assertEqual(turn["speaker"], "Speaker 1")
        self.assertAlmostEqual(ratio, 0.5, places=2)

    def test_best_turn_no_overlap_returns_empty_and_zero(self) -> None:
        segment = self._segment(0, 1000)
        turns = [{"speaker": "Speaker 1", "startMs": 2000, "endMs": 3000, "confidence": 0.9}]
        turn, ratio = voice_best_turn(segment, turns)
        self.assertEqual(turn, {})
        self.assertAlmostEqual(ratio, 0.0, places=2)

    def test_best_turn_prefers_higher_weighted_score(self) -> None:
        segment = self._segment(0, 1000)
        turns = [
            {"speaker": "Speaker 1", "startMs": 0, "endMs": 600, "confidence": 0.9},
            {"speaker": "Speaker 2", "startMs": 400, "endMs": 1000, "confidence": 0.5},
        ]
        turn, ratio = voice_best_turn(segment, turns)
        self.assertEqual(turn["speaker"], "Speaker 1")

    def test_segment_with_speaker_dynamic_confidence(self) -> None:
        segment = self._segment(0, 1000)
        assignment = {"speaker": "Speaker 1", "confidence": 0.9}
        result = _segment_with_speaker(segment, assignment, overlap_ratio=0.8)
        self.assertEqual(result.speaker, "Speaker 1")
        self.assertAlmostEqual(result.confidence, 0.72, places=2)

    def test_segment_with_speaker_full_overlap(self) -> None:
        segment = self._segment(0, 1000)
        assignment = {"speaker": "Speaker 1", "confidence": 0.9}
        result = _segment_with_speaker(segment, assignment, overlap_ratio=1.0)
        self.assertAlmostEqual(result.confidence, 0.9, places=2)

    def test_merge_diarization_low_overlap_keeps_unknown(self) -> None:
        segments = [self._segment(0, 1000)]
        payload = {
            "turns": [
                {"speaker": "Speaker 1", "startMs": 950, "endMs": 1000, "confidence": 0.9},
            ]
        }
        result = _merge_diarization_payload(payload, segments)
        self.assertEqual(result[0].speaker, "unknown")

    def test_merge_diarization_high_overlap_assigns_speaker(self) -> None:
        segments = [self._segment(0, 1000)]
        payload = {
            "turns": [
                {"speaker": "Speaker 1", "startMs": 0, "endMs": 1000, "confidence": 0.9},
            ]
        }
        result = _merge_diarization_payload(payload, segments)
        self.assertEqual(result[0].speaker, "Speaker 1")


class TestDiarizationRunnerMatching(unittest.TestCase):
    """Test overlap ratio matching in model_runners/diarization.py"""

    def _segment_dict(self, start_ms: int, end_ms: int) -> dict:
        return {"id": "seg-001", "speaker": "unknown", "startMs": start_ms, "endMs": end_ms}

    def test_best_turn_returns_tuple(self) -> None:
        seg = self._segment_dict(0, 1000)
        turns = [{"speaker": "Speaker 1", "startMs": 0, "endMs": 1000, "confidence": 0.9}]
        turn, ratio = runner_best_turn(seg, turns)
        self.assertEqual(turn["speaker"], "Speaker 1")
        self.assertAlmostEqual(ratio, 1.0, places=2)

    def test_best_turn_partial_overlap(self) -> None:
        seg = self._segment_dict(0, 1000)
        turns = [{"speaker": "Speaker 1", "startMs": 500, "endMs": 1500, "confidence": 0.9}]
        turn, ratio = runner_best_turn(seg, turns)
        self.assertAlmostEqual(ratio, 0.5, places=2)

    def test_best_turn_no_overlap(self) -> None:
        seg = self._segment_dict(0, 1000)
        turns = [{"speaker": "Speaker 1", "startMs": 2000, "endMs": 3000, "confidence": 0.9}]
        turn, ratio = runner_best_turn(seg, turns)
        self.assertEqual(turn, {})
        self.assertAlmostEqual(ratio, 0.0, places=2)

    def test_dynamic_confidence_scales_with_ratio(self) -> None:
        self.assertAlmostEqual(_dynamic_confidence(0.9, 1.0), 0.9, places=2)
        self.assertAlmostEqual(_dynamic_confidence(0.9, 0.5), 0.45, places=2)
        self.assertAlmostEqual(_dynamic_confidence(0.9, 0.1), 0.1, places=2)

    def test_dynamic_confidence_clamped(self) -> None:
        self.assertGreaterEqual(_dynamic_confidence(0.9, 1.0), 0.1)
        self.assertLessEqual(_dynamic_confidence(0.9, 1.0), 0.99)

    def test_min_overlap_threshold_short_segment(self) -> None:
        self.assertEqual(_min_overlap_threshold(300), 0.05)

    def test_min_overlap_threshold_normal_segment(self) -> None:
        self.assertEqual(_min_overlap_threshold(1000), 0.10)

    def test_assign_segments_low_overlap_keeps_unknown(self) -> None:
        segments = [self._segment_dict(0, 1000)]
        turns = [{"speaker": "Speaker 1", "startMs": 950, "endMs": 1000, "confidence": 0.9}]
        result = _assign_segments(segments, turns)
        self.assertEqual(result[0]["speaker"], "unknown")

    def test_assign_segments_high_overlap_assigns_speaker(self) -> None:
        segments = [self._segment_dict(0, 1000)]
        turns = [{"speaker": "Speaker 1", "startMs": 0, "endMs": 1000, "confidence": 0.9}]
        result = _assign_segments(segments, turns)
        self.assertEqual(result[0]["speaker"], "Speaker 1")
        self.assertGreater(result[0]["confidence"], 0.5)


if __name__ == "__main__":
    unittest.main()
