"""Contract for processed meeting intelligence providers."""

from typing import Protocol

from backend.models.meeting_models import Meeting, MeetingAsset
from backend.providers.transcript_types import TranscriptSegment

SCHEMA_VERSION = "meeting-intelligence-result.v1"


class AnalysisProvider(Protocol):
    provider_name: str
    provider_model: str
    last_provider_name: str
    last_provider_model: str

    def build_result(
        self,
        *,
        meeting: Meeting,
        asset: MeetingAsset,
        transcript_segments: list[TranscriptSegment],
        detected_language: str | None = None,
    ) -> dict:
        ...

    def build_window_result(
        self,
        *,
        meeting: Meeting,
        asset: MeetingAsset,
        transcript_segments: list[TranscriptSegment],
        detected_language: str | None = None,
    ) -> dict:
        ...
