"""Contracts and data types for the voice processing provider boundary."""

from dataclasses import dataclass
from typing import Protocol

from backend.models.meeting_models import MeetingAsset
from backend.providers.transcript_types import TranscriptSegment


@dataclass(frozen=True)
class AudioPreprocessingResult:
    source_object_key: str
    working_path: str | None
    duration_ms: int | None
    sample_rate_hz: int | None
    channel_count: int | None
    warnings: list[str]


@dataclass(frozen=True)
class SpeechRegion:
    start_ms: int
    end_ms: int
    confidence: float


@dataclass(frozen=True)
class SpeakerTurn:
    start_ms: int
    end_ms: int
    speaker: str
    confidence: float


class AudioPreprocessor(Protocol):
    provider_name: str
    provider_model: str

    def preprocess(self, asset: MeetingAsset) -> AudioPreprocessingResult:
        ...


class VADProvider(Protocol):
    provider_name: str
    provider_model: str

    def detect_speech(self, audio: AudioPreprocessingResult) -> list[SpeechRegion]:
        ...


class ASRProvider(Protocol):
    provider_name: str
    provider_model: str

    def transcribe_audio(
        self,
        *,
        audio: AudioPreprocessingResult,
        speech_regions: list[SpeechRegion],
    ) -> list[TranscriptSegment]:
        ...


class DiarizationProvider(Protocol):
    provider_name: str
    provider_model: str

    def assign_speakers(
        self,
        *,
        audio: AudioPreprocessingResult,
        transcript_segments: list[TranscriptSegment],
    ) -> list[TranscriptSegment]:
        ...
