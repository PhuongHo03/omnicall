from dataclasses import dataclass
import time
from typing import Callable

from backend.providers.llm import FallbackLLMProviderError, get_configured_primary_model_name
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
        analysis_llm = getattr(self.provider, "llm_provider", None)
        primary_llm = getattr(analysis_llm, "primary", analysis_llm)
        self.emit_stage_started(
            stage="analysis",
            message="Meeting intelligence analysis started.",
            meeting=meeting,
            asset=asset,
            provider=getattr(primary_llm, "provider_name", self.provider.provider_name),
            model=(
                get_configured_primary_model_name(analysis_llm)
                if analysis_llm is not None
                else self.provider.provider_model
            ),
        )
        try:
            result_json = self._build_result(
                meeting=meeting,
                asset=asset,
                transcript_segments=transcript_segments,
                detected_language=detected_language,
                transcription_provider=transcription_provider,
            )
        except FallbackLLMProviderError as exc:
            common = {
                "flow": "processing",
                "workspace_id": meeting.owner_user_id,
                "meeting_id": meeting.id,
                "meeting_name": meeting.title,
                "file": asset_log_context(asset),
                "executor_type": "llm",
                "fallback_used": True,
                "duration_ms": elapsed_ms(started),
            }
            self.emit(
                level="error",
                stage="analysis_llm_primary",
                status="failed",
                message="Primary analysis LLM failed; fallback was activated.",
                provider=exc.primary_provider,
                model=exc.primary_model,
                configured_provider=exc.primary_provider,
                configured_model=exc.primary_model,
                error_type=type(exc.primary_error).__name__,
                error_message=str(exc.primary_error),
                **common,
            )
            self.emit(
                level="error",
                stage="analysis_llm_fallback",
                status="failed",
                message="Fallback analysis LLM also failed.",
                provider=exc.fallback_provider,
                model=exc.fallback_model,
                effective_provider=exc.fallback_provider,
                effective_model=exc.fallback_model,
                error_type=type(exc.fallback_error).__name__,
                error_message=str(exc.fallback_error),
                **common,
            )
            raise
        provider_executions = result_json.get("source", {}).get("providerExecutions", [])
        fallback_execution = next(
            (
                item for item in provider_executions
                if isinstance(item, dict) and item.get("fallbackUsed") is True
            ),
            None,
        )
        if getattr(analysis_llm, "last_fallback_used", False) or fallback_execution is not None:
            primary = getattr(analysis_llm, "primary", None)
            self.emit(
                level="error",
                flow="processing",
                stage="analysis_llm_primary",
                status="failed",
                message="One or more primary analysis LLM calls failed; fallback was activated.",
                workspace_id=meeting.owner_user_id,
                meeting_id=meeting.id,
                meeting_name=meeting.title,
                file=asset_log_context(asset),
                provider=getattr(primary, "provider_name", None),
                model=getattr(primary, "model_name", None),
                executor_type="llm",
                configured_provider=getattr(primary, "provider_name", None),
                configured_model=getattr(primary, "model_name", None),
                fallback_used=True,
                duration_ms=elapsed_ms(started),
                details={"providerExecutions": provider_executions},
                error_type=(
                    (fallback_execution or {}).get("primaryErrorType")
                    or getattr(analysis_llm, "last_primary_error_type", None)
                    or "LLMProviderError"
                ),
                error_message=(
                    (fallback_execution or {}).get("primaryErrorMessage")
                    or getattr(analysis_llm, "last_primary_error_message", None)
                    or "Primary LLM provider failed."
                ),
            )
            self.emit(
                level="info",
                flow="processing",
                stage="analysis_llm_fallback",
                status="succeeded",
                message="Fallback analysis LLM completed the bounded extraction.",
                workspace_id=meeting.owner_user_id,
                meeting_id=meeting.id,
                meeting_name=meeting.title,
                file=asset_log_context(asset),
                provider=result_json.get("source", {}).get("llmProvider") or self.provider.last_provider_name,
                model=result_json.get("source", {}).get("analysisModel") or self.provider.last_provider_model,
                executor_type="llm",
                effective_provider=result_json.get("source", {}).get("llmProvider") or self.provider.last_provider_name,
                effective_model=result_json.get("source", {}).get("analysisModel") or self.provider.last_provider_model,
                fallback_used=True,
                duration_ms=elapsed_ms(started),
                details={"providerExecutions": provider_executions},
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
            executor_type="llm",
            configured_provider=getattr(primary_llm, "provider_name", None),
            configured_model=(
                get_configured_primary_model_name(analysis_llm)
                if analysis_llm is not None
                else self.provider.provider_model
            ),
            effective_provider=runtime_provider,
            effective_model=runtime_model,
            fallback_used=bool(result_json.get("source", {}).get("fallbackUsed", False)),
            duration_ms=elapsed_ms(started),
            details={
                "schemaVersion": result_json.get("schemaVersion"),
                "summaryPresent": bool(result_json.get("summaries", {}).get("executive", {}).get("text")),
                "knowledgeSections": sum(
                    1
                    for key in ("facts", "events", "entities", "relationships", "topics", "actions", "decisions", "risks", "questions")
                    if result_json.get(key)
                ),
                "providerExecutions": provider_executions,
            },
        )
        result_json.setdefault("source", {})
        result_json["source"]["transcriptionProvider"] = transcription_provider.last_provider_name
        result_json["source"]["transcriptionModel"] = transcription_provider.last_provider_model
        if getattr(transcription_provider, "last_voice_metadata", None):
            result_json["source"]["voiceMetadata"] = transcription_provider.last_voice_metadata
            append_voice_quality_warnings(result_json, transcription_provider.last_voice_metadata)
        return AnalysisStageResult(result_json=result_json, duration_ms=elapsed_ms(started))

    def _build_result(
        self,
        *,
        meeting,
        asset,
        transcript_segments: list,
        detected_language: str | None,
        transcription_provider,
    ) -> dict:
        if self.extraction_service is not None:
            extraction_result = self.extraction_service.run(
                meeting=meeting,
                asset=asset,
                transcript_segments=transcript_segments,
                detected_language=detected_language,
                transcription_metadata={
                    "provider": getattr(transcription_provider, "last_provider_name", None),
                    "model": getattr(transcription_provider, "last_provider_model", None),
                    "voiceMetadata": getattr(transcription_provider, "last_voice_metadata", {}) or {},
                },
            )
            return extraction_result.result_json
        return self.provider.build_result(
            meeting=meeting,
            asset=asset,
            transcript_segments=transcript_segments,
            detected_language=detected_language,
        )
