from dataclasses import dataclass
import time
from typing import Any, Callable

from backend.services.processing.observability import asset_log_context, elapsed_ms
from backend.services.processing.voice_events import emit_voice_stage_results


@dataclass(frozen=True)
class TranscriptionStageResult:
    segments: list[Any]
    detected_language: str | None
    duration_ms: int


class TranscriptionStage:
    def __init__(self, provider, emit: Callable[..., None], emit_stage_started: Callable[..., None]) -> None:
        self.provider = provider
        self.emit = emit
        self.emit_stage_started = emit_stage_started

    def run(self, *, meeting, asset) -> TranscriptionStageResult:
        started = time.perf_counter()
        self.emit_stage_started(
            stage="transcription",
            message="Transcript extraction started.",
            meeting=meeting,
            asset=asset,
            provider=self.provider.provider_name,
            model=self.provider.provider_model,
            details={},
        )
        segments = self.provider.transcribe(meeting, asset)
        duration_ms = elapsed_ms(started)
        self.emit(
            level="info",
            flow="processing",
            stage="transcription",
            status="succeeded",
            message="Transcript extraction completed.",
            workspace_id=meeting.owner_user_id,
            meeting_id=meeting.id,
            meeting_name=meeting.title,
            file=asset_log_context(asset),
            provider=self.provider.last_provider_name,
            model=self.provider.last_provider_model,
            duration_ms=duration_ms,
            details={"segmentCount": len(segments)},
        )
        emit_voice_stage_results(
            emit=self.emit,
            transcription_provider=self.provider,
            meeting=meeting,
            asset=asset,
            transcript_segments=segments,
            transcription_duration_ms=duration_ms,
        )
        metadata = getattr(self.provider, "last_voice_metadata", {}) or {}
        return TranscriptionStageResult(
            segments=segments,
            detected_language=metadata.get("detectedLanguage"),
            duration_ms=duration_ms,
        )
