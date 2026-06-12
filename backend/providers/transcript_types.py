from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptSegment:
    id: str
    speaker: str
    start_ms: int
    end_ms: int
    text: str
    confidence: float
