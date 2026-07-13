from dataclasses import dataclass
import time
from typing import Callable

from backend.services.processing.observability import asset_log_context, elapsed_ms
from backend.services.processing.result_validation import append_voice_quality_warnings


@dataclass(frozen=True)
class AnalysisStageResult:
    result_json: dict
    duration_ms: int


class AnalysisStage:
    def __init__(self, provider, emit: Callable[..., None], emit_stage_started: Callable[..., None], extraction_service=None) -> None:
        self.provider = provider
        self.emit = emit
        self.emit_stage_started = emit_stage_started
        self.extraction_service = extraction_service

    def run(
        self,
        *,
        meeting,
        asset,
        transcript_segments: list,
        detected_language: str | None,
        transcription_provider,
    ) -> AnalysisStageResult:
        started = time.perf_counter()
        self.emit_stage_started(
            stage="analysis",
            message="Meeting intelligence analysis started.",
            meeting=meeting,
            asset=asset,
            provider=self.provider.provider_name,
            model=self.provider.provider_model,
        )
        if self.extraction_service is not None:
            extraction_result = self.extraction_service.run(
                meeting=meeting,
                asset=asset,
                transcript_segments=transcript_segments,
                detected_language=detected_language,
            )
            result_json = extraction_result.result_json
        else:
            result_json = self.provider.build_result(
                meeting=meeting,
                asset=asset,
                transcript_segments=transcript_segments,
                detected_language=detected_language,
            )
        analysis_llm = getattr(self.provider, "llm_provider", None)
        if getattr(analysis_llm, "last_fallback_used", False):
            primary = getattr(analysis_llm, "primary", None)
            self.emit(
                level="error",
                flow="processing",
                stage="analysis_llm_primary",
                status="failed",
                message="Primary analysis LLM failed; Ollama fallback was activated.",
                workspace_id=meeting.owner_user_id,
                meeting_id=meeting.id,
                meeting_name=meeting.title,
                file=asset_log_context(asset),
                provider=getattr(primary, "provider_name", None),
                model=getattr(primary, "model_name", None),
                duration_ms=elapsed_ms(started),
                error_type=getattr(analysis_llm, "last_primary_error_type", "LLMProviderError"),
                error_message=getattr(analysis_llm, "last_primary_error_message", "Primary LLM provider failed."),
            )
        runtime_provider = result_json.get("source", {}).get("llmProvider") or self.provider.last_provider_name
        runtime_model = result_json.get("source", {}).get("analysisModel") or self.provider.last_provider_model
        self.emit(
            level="info",
            flow="processing",
            stage="analysis",
            status="succeeded",
            message="Meeting intelligence analysis completed.",
            workspace_id=meeting.owner_user_id,
            meeting_id=meeting.id,
            meeting_name=meeting.title,
            file=asset_log_context(asset),
            provider=runtime_provider,
            model=runtime_model,
            duration_ms=elapsed_ms(started),
            details={
                "schemaVersion": result_json.get("schemaVersion"),
                "summaryPresent": bool(result_json.get("summaries", {}).get("executive", {}).get("text")),
                "knowledgeSections": sum(
                    1
                    for key in ("facts", "events", "entities", "relationships", "topics", "actions", "decisions", "risks", "questions")
                    if result_json.get(key)
                ),
            },
        )
        result_json.setdefault("source", {})
        result_json["source"]["transcriptionProvider"] = transcription_provider.last_provider_name
        result_json["source"]["transcriptionModel"] = transcription_provider.last_provider_model
        if getattr(transcription_provider, "last_voice_metadata", None):
            result_json["source"]["voiceMetadata"] = transcription_provider.last_voice_metadata
            append_voice_quality_warnings(result_json, transcription_provider.last_voice_metadata)
        return AnalysisStageResult(result_json=result_json, duration_ms=elapsed_ms(started))
