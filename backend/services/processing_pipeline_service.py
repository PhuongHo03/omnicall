import time

from sqlalchemy.orm import Session

from backend.models.enums import MeetingStatus
from backend.configs.settings import Settings, get_settings
from backend.providers.analysis_provider import SCHEMA_VERSION, AnalysisProvider
from backend.providers.lock_provider import RedisLockProvider
from backend.providers.transcription_provider import LocalTranscriptionProvider
from backend.repositories.meeting_repository import (
    MeetingAssetRepository,
    MeetingIntelligenceResultRepository,
    MeetingRepository,
)
from backend.services.retrieval_index_service import RetrievalIndexService
from backend.services.operational_log_service import OperationalLogService


class ProcessingPipelineService:
    def __init__(
        self,
        session: Session,
        lock_provider: RedisLockProvider,
        transcription_provider: LocalTranscriptionProvider,
        analysis_provider: AnalysisProvider,
        retrieval_index: RetrievalIndexService | None = None,
        settings: Settings | None = None,
        operational_logs: OperationalLogService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.lock_provider = lock_provider
        self.transcription_provider = transcription_provider
        self.analysis_provider = analysis_provider
        self.meetings = MeetingRepository(session)
        self.assets = MeetingAssetRepository(session)
        self.results = MeetingIntelligenceResultRepository(session)
        self.retrieval_index = retrieval_index or RetrievalIndexService(session)
        self.operational_logs = operational_logs

    def process_meeting(self, *, meeting_id: str) -> dict[str, str]:
        lock_key = f"lock:meeting-processing:{meeting_id}"
        lock_token = self.lock_provider.acquire(lock_key)
        if lock_token is None:
            self._emit(
                level="info",
                flow="processing",
                stage="worker_lock",
                status="skipped",
                message="Processing skipped because the meeting lock is already held.",
                meeting_id=meeting_id,
                provider="redis-lock",
            )
            return {"meeting_id": meeting_id, "status": "locked"}

        try:
            return self._process_with_lock(meeting_id=meeting_id)
        finally:
            self.lock_provider.release(lock_key, lock_token)

    def _process_with_lock(self, *, meeting_id: str) -> dict[str, str]:
        meeting = self.meetings.get(meeting_id)
        if meeting is None:
            self._emit(
                level="error",
                flow="processing",
                stage="worker_received",
                status="failed",
                message="Worker received an unknown meeting.",
                meeting_id=meeting_id,
                provider="celery",
                error_type="MissingMeeting",
                error_message="Meeting was not found.",
            )
            return {"meeting_id": meeting_id, "status": "missing"}

        if meeting.status == MeetingStatus.READY:
            self._emit(
                level="info",
                flow="processing",
                stage="worker_received",
                status="skipped",
                message="Worker skipped an already completed processing job.",
                workspace_id=meeting.owner_user_id if meeting else None,
                meeting_id=meeting_id,
                provider="celery",
            )
            return {"meeting_id": meeting_id, "status": "skipped"}

        if meeting.status == MeetingStatus.FAILED:
            self.meetings.update_status(meeting, MeetingStatus.QUEUED)
            self.session.commit()

        asset = self.assets.get_latest_for_meeting(meeting_id)
        if asset is None:
            self.meetings.update_status(meeting, MeetingStatus.FAILED, "Meeting or uploaded asset was not found.")
            self.session.commit()
            self._emit(
                level="error",
                flow="processing",
                stage="worker_received",
                status="failed",
                message="Worker could not load the meeting or uploaded file.",
                workspace_id=meeting.owner_user_id if meeting else None,
                meeting_id=meeting_id,
                meeting_name=meeting.title if meeting is not None else None,
                file=_asset_log_context(asset),
                provider="celery",
                error_type="MissingMeetingAsset",
                error_message="Meeting or uploaded asset was not found.",
            )
            return {"meeting_id": meeting_id, "status": "failed"}

        self._emit(
            level="info",
            flow="processing",
            stage="worker_received",
            status="succeeded",
            message="Worker received the processing job.",
            workspace_id=meeting.owner_user_id,
            meeting_id=meeting.id,
            meeting_name=meeting.title,
            file=_asset_log_context(asset),
            provider="celery",
        )
        self.meetings.update_status(meeting, MeetingStatus.PROCESSING)
        self.meetings.increment_attempts(meeting)
        self.session.commit()
        self._emit(
            level="info",
            flow="processing",
            stage="processing",
            status="started",
            message="Meeting processing started.",
            workspace_id=meeting.owner_user_id,
            meeting_id=meeting.id,
            meeting_name=meeting.title,
            file=_asset_log_context(asset),
        )

        processing_started = time.perf_counter()
        current_stage = "transcription"
        stage_started = time.perf_counter()
        try:
            transcription_route = self._transcription_route(asset)
            self._emit_stage_started(
                stage=current_stage,
                message="Transcript extraction started.",
                meeting=meeting,
                asset=asset,
                provider=transcription_route["provider"],
                model=transcription_route["model"],
                details=transcription_route["details"],
            )
            transcript_segments = self.transcription_provider.transcribe(meeting, asset)
            detected_language = self.transcription_provider.last_voice_metadata.get("detectedLanguage")
            transcription_duration_ms = _elapsed_ms(stage_started)
            self._emit(
                level="info",
                flow="processing",
                stage="transcription",
                status="succeeded",
                message="Transcript extraction completed.",
                workspace_id=meeting.owner_user_id,
                meeting_id=meeting.id,
                meeting_name=meeting.title,
                file=_asset_log_context(asset),
                provider=self.transcription_provider.last_provider_name,
                model=self.transcription_provider.last_provider_model,
                duration_ms=transcription_duration_ms,
                details={"segmentCount": len(transcript_segments)},
            )
            self._emit_voice_stage_results(
                meeting=meeting,
                asset=asset,
                transcript_segments=transcript_segments,
                transcription_duration_ms=transcription_duration_ms,
            )

            current_stage = "analysis"
            stage_started = time.perf_counter()
            self._emit_stage_started(
                stage=current_stage,
                message="Meeting intelligence analysis started.",
                meeting=meeting,
                asset=asset,
                provider=self.analysis_provider.provider_name,
                model=self.analysis_provider.provider_model,
            )
            result_json = self.analysis_provider.build_result(
                meeting=meeting,
                asset=asset,
                transcript_segments=transcript_segments,
                detected_language=detected_language,
            )
            analysis_llm = getattr(self.analysis_provider, "llm_provider", None)
            if getattr(analysis_llm, "last_fallback_used", False):
                primary = getattr(analysis_llm, "primary", None)
                self._emit(
                    level="error",
                    flow="processing",
                    stage="analysis_llm_primary",
                    status="failed",
                    message="Primary analysis LLM failed; Ollama fallback was activated.",
                    workspace_id=meeting.owner_user_id,
                    meeting_id=meeting.id,
                    meeting_name=meeting.title,
                    file=_asset_log_context(asset),
                    provider=getattr(primary, "provider_name", None),
                    model=getattr(primary, "model_name", None),
                    duration_ms=_elapsed_ms(stage_started),
                    error_type=getattr(analysis_llm, "last_primary_error_type", "LLMProviderError"),
                    error_message=getattr(analysis_llm, "last_primary_error_message", "Primary LLM provider failed."),
                )
            runtime_provider = result_json.get("source", {}).get("llmProvider") or self.analysis_provider.last_provider_name
            runtime_model = result_json.get("source", {}).get("analysisModel") or self.analysis_provider.last_provider_model
            self._emit(
                level="info",
                flow="processing",
                stage=current_stage,
                status="succeeded",
                message="Meeting intelligence analysis completed.",
                workspace_id=meeting.owner_user_id,
                meeting_id=meeting.id,
                meeting_name=meeting.title,
                file=_asset_log_context(asset),
                provider=runtime_provider,
                model=runtime_model,
                duration_ms=_elapsed_ms(stage_started),
                details={
                    "schemaVersion": result_json.get("schemaVersion"),
                    "summaryPresent": bool(result_json.get("summary", {}).get("executive")),
                    "analysisSections": len(result_json.get("analysis", {})),
                },
            )
            result_json.setdefault("source", {})
            result_json["source"]["transcriptionProvider"] = self.transcription_provider.last_provider_name
            result_json["source"]["transcriptionModel"] = self.transcription_provider.last_provider_model
            if getattr(self.transcription_provider, "last_voice_metadata", None):
                result_json["source"]["voiceMetadata"] = self.transcription_provider.last_voice_metadata
                _append_voice_quality_warnings(result_json, self.transcription_provider.last_voice_metadata)
            current_stage = "result_validation"
            stage_started = time.perf_counter()
            self._validate_result_json(result_json)
            self._emit(
                level="info",
                flow="processing",
                stage=current_stage,
                status="succeeded",
                message="Processed meeting JSON validated.",
                workspace_id=meeting.owner_user_id,
                meeting_id=meeting.id,
                meeting_name=meeting.title,
                file=_asset_log_context(asset),
                duration_ms=_elapsed_ms(stage_started),
                details={"schemaVersion": SCHEMA_VERSION, "segmentCount": len(transcript_segments)},
            )

            current_stage = "result_persistence"
            stage_started = time.perf_counter()
            result = self.results.upsert(
                meeting_id=meeting.id,
                
                schema_version=SCHEMA_VERSION,
                provider_name=self.analysis_provider.last_provider_name,
                provider_model=self.analysis_provider.last_provider_model,
                result_json=result_json,
            )
            self._emit(
                level="info",
                flow="processing",
                stage=current_stage,
                status="succeeded",
                message="Processed meeting intelligence JSON persisted.",
                workspace_id=meeting.owner_user_id,
                meeting_id=meeting.id,
                meeting_name=meeting.title,
                file=_asset_log_context(asset),
                duration_ms=_elapsed_ms(stage_started),
                details={
                    "resultId": result.id,
                    "segmentCount": len(result_json["transcript"]["segments"]),
                },
            )

            current_stage = "retrieval_index"
            stage_started = time.perf_counter()
            retrieval_chunks = self.retrieval_index.rebuild_for_result(result)
            index_metadata = self.retrieval_index.last_index_metadata
            self._emit(
                level="info",
                flow="processing",
                stage="embedding",
                status="succeeded",
                message="Retrieval chunks and text embeddings generated.",
                workspace_id=meeting.owner_user_id,
                meeting_id=meeting.id,
                meeting_name=meeting.title,
                file=_asset_log_context(asset),
                provider=index_metadata.get("embeddingProvider"),
                model=index_metadata.get("embeddingModel"),
                duration_ms=index_metadata.get("embeddingDurationMs"),
                details={"chunkCount": len(retrieval_chunks)},
            )
            vector_metadata = index_metadata.get("vector", {})
            vector_failed = vector_metadata.get("status") == "failed"
            self._emit(
                level="error" if vector_failed else "info",
                flow="processing",
                stage="vector_upsert",
                status="failed" if vector_failed else "succeeded",
                message="Vector index update failed." if vector_failed else "Vector index updated.",
                workspace_id=meeting.owner_user_id,
                meeting_id=meeting.id,
                meeting_name=meeting.title,
                file=_asset_log_context(asset),
                provider=index_metadata.get("vectorProvider"),
                model=self.settings.milvus_collection,
                duration_ms=index_metadata.get("vectorDurationMs"),
                details=vector_metadata,
                error_type="VectorProviderError" if vector_failed else None,
                error_message=vector_metadata.get("error") if vector_failed else None,
            )

            self.meetings.update_status(meeting, MeetingStatus.READY)
            self.session.commit()
            self._emit(
                level="info",
                flow="processing",
                stage="result",
                status="succeeded",
                message="Meeting processing completed and the result is ready.",
                workspace_id=meeting.owner_user_id,
                meeting_id=meeting.id,
                meeting_name=meeting.title,
                file=_asset_log_context(asset),
                duration_ms=_elapsed_ms(processing_started),
                details={
                    "resultId": result.id,
                    "schemaVersion": SCHEMA_VERSION,
                    "segmentCount": len(transcript_segments),
                    "chunkCount": len(retrieval_chunks),
                },
            )
            return {"meeting_id": meeting.id, "status": "succeeded"}
        except Exception as exc:
            self.session.rollback()
            meeting = self.meetings.get(meeting_id)
            if meeting is None:
                return {"meeting_id": meeting_id, "status": "missing"}
            safe_reason = "Meeting processing failed. Please retry later."
            self.meetings.update_status(meeting, MeetingStatus.FAILED, safe_reason)
            self.session.commit()
            failed_stage = self._transcription_failure_stage() if current_stage == "transcription" else current_stage
            provider, model = self._stage_model(failed_stage)
            self._emit(
                level="error",
                flow="processing",
                stage=failed_stage,
                status="failed",
                message=f"Meeting processing failed during {failed_stage.replace('_', ' ')}.",
                workspace_id=meeting.owner_user_id,
                meeting_id=meeting.id,
                meeting_name=meeting.title,
                file=_asset_log_context(asset),
                provider=provider,
                model=model,
                duration_ms=_elapsed_ms(stage_started),
                details={"safeReason": safe_reason},
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return {"meeting_id": meeting.id, "status": "failed"}

    def _emit_stage_started(
        self,
        *,
        stage: str,
        message: str,
        meeting,
        asset,
        provider: str,
        model: str,
        details: dict | None = None,
    ) -> None:
        self._emit(
            level="info",
            flow="processing",
            stage=stage,
            status="started",
            message=message,
            workspace_id=meeting.owner_user_id,
            meeting_id=meeting.id,
            meeting_name=meeting.title,
            file=_asset_log_context(asset),
            provider=provider,
            model=model,
            details=details or {},
        )

    def _transcription_route(self, asset) -> dict:
        return {
            "provider": self.transcription_provider.provider_name,
            "model": self.transcription_provider.provider_model,
            "details": {},
        }

    def _emit_voice_stage_results(
        self,
        *,
        meeting,
        asset,
        transcript_segments: list,
        transcription_duration_ms: int,
    ) -> None:
        metadata = getattr(self.transcription_provider, "last_voice_metadata", {}) or {}
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
            "file": _asset_log_context(asset),
        }
        self._emit(
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
        self._emit(
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
        self._emit(
            **common,
            stage="asr",
            message="Automatic speech recognition completed.",
            provider=metadata.get("asrProvider") or self.transcription_provider.last_provider_name,
            model=metadata.get("asrModel") or self.transcription_provider.last_provider_model,
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
            self._emit(
                **common,
                stage="diarization",
                message="Speaker diarization completed.",
                provider=metadata.get("diarizationProvider"),
                model=metadata.get("diarizationModel"),
                details={"segmentCount": segment_count, "speakerCount": speakers or None},
            )

    def _stage_model(self, stage: str) -> tuple[str | None, str | None]:
        voice_metadata = getattr(self.transcription_provider, "last_voice_metadata", {}) or {}
        if stage == "audio_preprocessing":
            return voice_metadata.get("audioPreprocessor"), voice_metadata.get("audioPreprocessorModel")
        if stage == "vad":
            return voice_metadata.get("vadProvider"), voice_metadata.get("vadModel")
        if stage == "asr":
            return (
                voice_metadata.get("asrProvider") or getattr(self.transcription_provider, "last_provider_name", None),
                voice_metadata.get("asrModel") or getattr(self.transcription_provider, "last_provider_model", None),
            )
        if stage == "diarization":
            return voice_metadata.get("diarizationProvider"), voice_metadata.get("diarizationModel")
        if stage == "transcription":
            return (
                getattr(self.transcription_provider, "last_provider_name", self.transcription_provider.provider_name),
                getattr(self.transcription_provider, "last_provider_model", self.transcription_provider.provider_model),
            )
        if stage == "analysis":
            return (
                getattr(self.analysis_provider, "last_provider_name", self.analysis_provider.provider_name),
                getattr(self.analysis_provider, "last_provider_model", self.analysis_provider.provider_model),
            )
        if stage == "retrieval_index":
            return (
                self.retrieval_index.embedding_provider.provider_name,
                self.retrieval_index.embedding_provider.model_name,
            )
        return None, None

    def _transcription_failure_stage(self) -> str:
        metadata = getattr(self.transcription_provider, "last_voice_metadata", {}) or {}
        warnings = " ".join(str(item).lower() for item in metadata.get("warnings", []))
        if "diarization failed" in warnings:
            return "diarization"
        if "asr failed" in warnings:
            return "asr"
        if "preprocessing failed" in warnings:
            return "audio_preprocessing"
        return "transcription"

    def _emit(self, **event) -> None:
        if self.operational_logs is not None:
            self.operational_logs.emit(**event)

    @staticmethod
    def _validate_result_json(result_json: dict) -> None:
        required_top_level = {"schemaVersion", "meeting", "source", "transcript", "summary", "analysis", "citations", "quality"}
        missing = required_top_level.difference(result_json)
        if missing:
            raise ValueError(f"Processed result missing sections: {', '.join(sorted(missing))}")

        segments = result_json.get("transcript", {}).get("segments", [])
        if not segments:
            raise ValueError("Processed result must include at least one transcript segment.")

        summary = result_json.get("summary", {})
        if not summary.get("executive"):
            raise ValueError("Processed result must include an executive summary.")

        segment_ids = {segment.get("id") for segment in segments}
        citations = {citation.get("id"): citation for citation in result_json.get("citations", [])}
        for citation in citations.values():
            for segment_id in citation.get("segmentIds", []):
                if segment_id not in segment_ids:
                    raise ValueError(f"Citation references unknown transcript segment: {segment_id}")

        for item in _extract_indexed_insights(result_json):
            for citation_id in item.get("citationIds", []):
                if citation_id not in citations:
                    raise ValueError(f"Insight references unknown citation: {citation_id}")


def _extract_indexed_insights(result_json: dict) -> list[dict]:
    insights: list[dict] = []
    citations_by_id = {citation.get("id"): citation for citation in result_json.get("citations", [])}
    summary = result_json.get("summary", {})
    if summary.get("executive"):
        insights.append(
            {
                "section": "summary.executive",
                "itemId": "summary-executive",
                "title": "Executive summary",
                "text": summary["executive"],
                "citationIds": [],
                "segmentIds": [],
                "payload": summary,
            }
        )
    for index, item in enumerate(summary.get("detailed", []), start=1):
        if isinstance(item, dict):
            insights.append(_indexed_item("summary.detailed", index, item, citations_by_id))
    for index, item in enumerate(summary.get("keyPoints", []), start=1):
        if isinstance(item, dict):
            insights.append(_indexed_item("summary.keyPoints", index, item, citations_by_id))

    analysis = result_json.get("analysis", {})
    for section, values in analysis.items():
        if section == "emptySections" or not isinstance(values, list):
            continue
        for index, item in enumerate(values, start=1):
            if isinstance(item, dict):
                insights.append(_indexed_item(f"analysis.{section}", index, item, citations_by_id))
    return [insight for insight in insights if insight["text"].strip()]


def _indexed_item(section: str, index: int, item: dict, citations_by_id: dict[str, dict]) -> dict:
    citation_ids = list(item.get("citationIds", []))
    segment_ids = []
    for citation_id in citation_ids:
        segment_ids.extend(citations_by_id.get(citation_id, {}).get("segmentIds", []))
    return {
        "section": section,
        "itemId": item.get("id") or f"{section}-{index:03d}",
        "title": item.get("title") or item.get("name") or item.get("owner"),
        "text": _item_text(item),
        "citationIds": citation_ids,
        "segmentIds": list(dict.fromkeys(segment_ids or item.get("sourceSegmentIds", []))),
        "payload": item,
    }


def _item_text(item: dict) -> str:
    for key in ("text", "summary", "task", "question", "quote", "name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _append_voice_quality_warnings(result_json: dict, voice_metadata: dict) -> None:
    quality = result_json.setdefault("quality", {})
    warnings = quality.setdefault("warnings", [])
    if not isinstance(warnings, list):
        warnings = []
        quality["warnings"] = warnings

    source_kind = voice_metadata.get("sourceKind")
    if source_kind == "voice":
        warnings.append("Voice input was processed through the voice provider pipeline.")
        if voice_metadata.get("asrProvider"):
            warnings.append("Voice transcript was produced by the configured local ASR provider.")
        if voice_metadata.get("diarizationProvider"):
            warnings.append("Speaker labels were assigned by the configured local diarization provider.")
    elif source_kind == "text":
        warnings.append("Transcript was extracted from an uploaded text transcript.")
    elif source_kind:
        warnings.append(f"Transcript source kind: {source_kind}.")

    for warning in voice_metadata.get("warnings", []):
        if isinstance(warning, str) and warning:
            warnings.append(warning)
    warning = voice_metadata.get("warning")
    if isinstance(warning, str) and warning:
        warnings.append(warning)
    quality["warnings"] = list(dict.fromkeys(warnings))


def _asset_log_context(asset) -> dict:
    if asset is None:
        return {}
    return {
        "id": asset.id,
        "name": asset.file_name,
        "contentType": asset.content_type,
        "sizeBytes": asset.size_bytes,
        "objectKey": asset.object_key,
    }


def _job_log_context(meeting) -> dict:
    return {
        "id": meeting.id,
        "attempt": meeting.attempts,
        "queue": "meeting-processing",
        "taskName": "omnicall.processing.process_meeting",
        "status": str(meeting.status),
    }


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
