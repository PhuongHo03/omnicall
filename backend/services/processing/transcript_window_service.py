import hashlib
import json
from dataclasses import dataclass



class TokenManager:
    """Small deterministic estimator used only for transcript window sizing."""

    def count_tokens(self, text: str) -> int:
        return max(1, int(len(text) * 0.25)) if text else 0


@dataclass(frozen=True)
class TranscriptWindow:
    window_id: str
    sequence_no: int
    segments: list
    start_ms: int | None
    end_ms: int | None
    token_count: int
    window_hash: str

    def as_record(self) -> dict:
        return {
            "windowId": self.window_id,
            "sequenceNo": self.sequence_no,
            "startMs": self.start_ms,
            "endMs": self.end_ms,
            "segmentIds": [segment.id for segment in self.segments],
            "tokenCount": self.token_count,
            "windowHash": self.window_hash,
        }


class TranscriptWindowService:
    """Build deterministic, bounded windows without duplicating transcript text."""

    def __init__(self, *, target_tokens: int = 2000, hard_limit_tokens: int = 2800, overlap_segments: int = 1) -> None:
        self.target_tokens = target_tokens
        self.hard_limit_tokens = hard_limit_tokens
        self.overlap_segments = max(0, overlap_segments)
        self.token_manager = TokenManager()

    def build(self, segments: list) -> list[TranscriptWindow]:
        windows: list[TranscriptWindow] = []
        current: list = []
        current_tokens = 0

        def flush() -> None:
            nonlocal current, current_tokens
            if not current:
                return
            sequence = len(windows) + 1
            windows.append(self._make_window(sequence, current, current_tokens))
            overlap = current[-self.overlap_segments :] if self.overlap_segments else []
            current = list(overlap)
            current_tokens = sum(self._segment_tokens(segment) for segment in current)

        for segment in segments:
            segment_tokens = self._segment_tokens(segment)
            if current and current_tokens + segment_tokens > self.target_tokens:
                flush()
            if current and current_tokens + segment_tokens > self.hard_limit_tokens:
                current = []
                current_tokens = 0
            current.append(segment)
            current_tokens += segment_tokens

        flush()
        return windows

    def _segment_tokens(self, segment) -> int:
        text = f"{segment.speaker or ''} {segment.text or ''}".strip()
        return self.token_manager.count_tokens(text)

    def _make_window(self, sequence: int, segments: list, token_count: int) -> TranscriptWindow:
        start_values = [segment.start_ms for segment in segments if isinstance(segment.start_ms, int)]
        end_values = [segment.end_ms for segment in segments if isinstance(segment.end_ms, int)]
        payload = [
            {
                "id": segment.id,
                "speaker": segment.speaker,
                "startMs": segment.start_ms,
                "endMs": segment.end_ms,
                "text": segment.text,
            }
            for segment in segments
        ]
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        return TranscriptWindow(
            window_id=f"window-{sequence:04d}",
            sequence_no=sequence,
            segments=list(segments),
            start_ms=min(start_values) if start_values else None,
            end_ms=max(end_values) if end_values else None,
            token_count=token_count,
            window_hash=digest,
        )
