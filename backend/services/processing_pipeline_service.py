import time

from sqlalchemy.orm import Session

from backend.models.enums import MeetingStatus
from backend.configs.settings import Settings, get_settings
from backend.providers.analysis import SCHEMA_VERSION, AnalysisProvider
from backend.providers.lock_provider import RedisLockProvider
from backend.providers.transcription_provider import LocalTranscriptionProvider
from backend.repositories.meeting_repository import (
    MeetingAssetRepository,
    MeetingIntelligenceResultRepository,
    MeetingRepository,
)
from backend.services.retrieval.index_service import RetrievalIndexService
from backend.services.operational_log_service import OperationalLogService
from backend.services.processing.observability import asset_log_context, elapsed_ms
from backend.services.processing.result_validation import validate_result_json
from backend.services.processing.analysis_stage import AnalysisStage
from backend.services.processing.persistence_stage import PersistenceStage
from backend.services.processing.retrieval_index_stage import RetrievalIndexStage
from backend.services.processing.transcription_stage import TranscriptionStage
from backend.services.processing.hierarchical_extraction_service import HierarchicalExtractionService
from backend.repositories.transcript_window_repository import TranscriptWindowRepository


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
        self.transcription_stage = TranscriptionStage(
            provider=self.transcription_provider,
            emit=self._emit,
            emit_stage_started=self._emit_stage_started,
        )
        self.analysis_stage = AnalysisStage(
            provider=self.analysis_provider,
            emit=self._emit,
            emit_stage_started=self._emit_stage_started,
            extraction_service=HierarchicalExtractionService(
                session=session,
                analysis_provider=self.analysis_provider,
                settings=self.settings,
            ),
        )
        self.persistence_stage = PersistenceStage(
            results_repository=self.results,
            emit=self._emit,
        )
        self.retrieval_index_stage = RetrievalIndexStage(
            retrieval_index=self.retrieval_index,
            settings=self.settings,
            emit=self._emit,
        )
        self.transcript_windows = TranscriptWindowRepository(session)

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
                file=asset_log_context(asset),
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
            file=asset_log_context(asset),
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
            file=asset_log_context(asset),
        )

        processing_started = time.perf_counter()
        current_stage = "transcription"
        stage_started = time.perf_counter()
        try:
            transcription_result = self.transcription_stage.run(meeting=meeting, asset=asset)
            transcript_segments = transcription_result.segments
            detected_language = transcription_result.detected_language

            current_stage = "analysis"
            stage_started = time.perf_counter()
            analysis_result = self.analysis_stage.run(
                meeting=meeting,
                asset=asset,
                transcript_segments=transcript_segments,
                detected_language=detected_language,
                transcription_provider=self.transcription_provider,
            )
            result_json = analysis_result.result_json
            current_stage = "result_validation"
            stage_started = time.perf_counter()
            validate_result_json(result_json)
            self._emit(
                level="info",
                flow="processing",
                stage=current_stage,
                status="succeeded",
                message="Processed meeting JSON validated.",
                workspace_id=meeting.owner_user_id,
                meeting_id=meeting.id,
                meeting_name=meeting.title,
                file=asset_log_context(asset),
                duration_ms=elapsed_ms(stage_started),
                details={"schemaVersion": SCHEMA_VERSION, "segmentCount": len(transcript_segments)},
            )

            current_stage = "result_persistence"
            stage_started = time.perf_counter()
            persistence_result = self.persistence_stage.run(
                meeting=meeting,
                asset=asset,
                result_json=result_json,
                provider_name=self.analysis_provider.last_provider_name,
                provider_model=self.analysis_provider.last_provider_model,
            )
            result = persistence_result.result
            extraction_generation = result_json.get("extraction", {}).get("generation")
            if extraction_generation:
                self.transcript_windows.attach_result(
                    meeting_id=meeting.id,
                    generation=extraction_generation,
                    result_id=result.id,
                )

            current_stage = "retrieval_index"
            stage_started = time.perf_counter()
            retrieval_result = self.retrieval_index_stage.run(
                meeting=meeting,
                asset=asset,
                result=result,
            )
            retrieval_chunks = retrieval_result.chunks

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
                file=asset_log_context(asset),
                duration_ms=elapsed_ms(processing_started),
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
                file=asset_log_context(asset),
                provider=provider,
                model=model,
                duration_ms=elapsed_ms(stage_started),
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
            file=asset_log_context(asset),
            provider=provider,
            model=model,
            details=details or {},
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
        validate_result_json(result_json)
