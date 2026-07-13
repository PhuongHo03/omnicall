from collections.abc import Callable

from backend.services.processing.observability import asset_log_context


def emit_voice_stage_results(
    *,
    emit: Callable[..., None],
    transcription_provider,
    meeting,
    asset,
    transcript_segments: list,
    transcription_duration_ms: int,
) -> None:
    metadata = getattr(transcription_provider, "last_voice_metadata", {}) or {}
    if metadata.get("sourceKind") != "voice":
        return

    segment_count = len(transcript_segments)
    common = {
        "level": "info",
        "flow": "processing",
        "status": "succeeded",
        "workspace_id": meeting.owner_user_id,
        "meeting_id": meeting.id,
        "meeting_name": meeting.title,
        "file": asset_log_context(asset),
    }
    emit(
        **common,
        stage="audio_preprocessing",
        message="Audio preprocessing completed.",
        provider=metadata.get("audioPreprocessor"),
        model=metadata.get("audioPreprocessorModel"),
        details={
            "durationMs": metadata.get("durationMs"),
            "sampleRateHz": metadata.get("sampleRateHz"),
            "channelCount": metadata.get("channelCount"),
            "warnings": metadata.get("warnings", []),
        },
    )
    emit(
        **common,
        stage="vad",
        message="Voice activity detection completed.",
        provider=metadata.get("vadProvider"),
        model=metadata.get("vadModel"),
        details={
            "speechRegionCount": metadata.get("speechRegionCount", 0),
            "speechRegions": metadata.get("speechRegions", []),
        },
    )
    emit(
        **common,
        stage="asr",
        message="Automatic speech recognition completed.",
        provider=metadata.get("asrProvider") or transcription_provider.last_provider_name,
        model=metadata.get("asrModel") or transcription_provider.last_provider_model,
        duration_ms=transcription_duration_ms,
        details={"segmentCount": segment_count, "audioDurationMs": metadata.get("durationMs")},
    )
    if metadata.get("diarizationProvider"):
        speakers = len(
            {
                segment.speaker
                for segment in transcript_segments
                if getattr(segment, "speaker", None)
            }
        )
        emit(
            **common,
            stage="diarization",
            message="Speaker diarization completed.",
            provider=metadata.get("diarizationProvider"),
            model=metadata.get("diarizationModel"),
            details={"segmentCount": segment_count, "speakerCount": speakers or None},
        )
