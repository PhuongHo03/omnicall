from sqlalchemy.orm import Session

from backend.models.enums import MeetingStatus, ProcessingJobStatus
from backend.configs.settings import Settings, get_settings
from backend.providers.analysis_provider import SCHEMA_VERSION, AnalysisProvider
from backend.providers.guardrail_provider import GuardrailProvider, get_guardrail_provider, safe_guardrail_check
from backend.providers.lock_provider import RedisLockProvider
from backend.providers.transcription_provider import LocalTranscriptionProvider
from backend.repositories.meeting_repository import (
    MeetingAssetRepository,
    MeetingInsightRepository,
    MeetingIntelligenceResultRepository,
    MeetingRepository,
    ProcessingJobRepository,
    TranscriptSegmentRepository,
)
from backend.services.retrieval_index_service import RetrievalIndexService


class ProcessingPipelineService:
    def __init__(
        self,
        session: Session,
        lock_provider: RedisLockProvider,
        transcription_provider: LocalTranscriptionProvider,
        analysis_provider: AnalysisProvider,
        guardrail_provider: GuardrailProvider | None = None,
        retrieval_index: RetrievalIndexService | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.lock_provider = lock_provider
        self.transcription_provider = transcription_provider
        self.analysis_provider = analysis_provider
        self.guardrail_provider = guardrail_provider or get_guardrail_provider()
        self.meetings = MeetingRepository(session)
        self.assets = MeetingAssetRepository(session)
        self.jobs = ProcessingJobRepository(session)
        self.results = MeetingIntelligenceResultRepository(session)
        self.segment_records = TranscriptSegmentRepository(session)
        self.insight_records = MeetingInsightRepository(session)
        self.retrieval_index = retrieval_index or RetrievalIndexService(session)

    def process_meeting(self, *, job_id: str, meeting_id: str) -> dict[str, str]:
        lock_key = f"lock:meeting-processing:{meeting_id}"
        lock_token = self.lock_provider.acquire(lock_key)
        if lock_token is None:
            return {"job_id": job_id, "meeting_id": meeting_id, "status": "locked"}

        try:
            return self._process_with_lock(job_id=job_id, meeting_id=meeting_id)
        finally:
            self.lock_provider.release(lock_key, lock_token)

    def _process_with_lock(self, *, job_id: str, meeting_id: str) -> dict[str, str]:
        job = self.jobs.get(job_id)
        if job is None or job.meeting_id != meeting_id:
            return {"job_id": job_id, "meeting_id": meeting_id, "status": "missing"}

        if job.status == ProcessingJobStatus.SUCCEEDED:
            return {"job_id": job_id, "meeting_id": meeting_id, "status": "skipped"}

        if job.status in {ProcessingJobStatus.FAILED, ProcessingJobStatus.RETRYING}:
            self.jobs.update_status(job, ProcessingJobStatus.RETRYING)
            self.session.commit()

        meeting = self.meetings.get_for_workspace(meeting_id, job.workspace_id)
        asset = self.assets.get_latest_for_meeting(meeting_id)
        if meeting is None or asset is None:
            self.jobs.update_status(
                job,
                ProcessingJobStatus.FAILED,
                safe_failure_reason="Meeting or uploaded asset was not found.",
                internal_error="missing_meeting_or_asset",
            )
            if meeting is not None:
                self.meetings.update_status(meeting, MeetingStatus.FAILED, "Meeting or uploaded asset was not found.")
            self.session.commit()
            return {"job_id": job_id, "meeting_id": meeting_id, "status": "failed"}

        self.jobs.update_status(job, ProcessingJobStatus.RUNNING, increment_attempts=True)
        self.meetings.update_status(meeting, MeetingStatus.PROCESSING)
        self.session.commit()

        try:
            transcript_segments = self.transcription_provider.transcribe(meeting, asset)
            transcript_guardrail = self._check_transcript_guardrail(meeting_id=meeting.id, transcript_segments=transcript_segments)
            if transcript_guardrail.get("action") == "block":
                raise ValueError("transcript_guardrail_blocked")
            result_json = self.analysis_provider.build_result(
                meeting=meeting,
                asset=asset,
                transcript_segments=transcript_segments,
            )
            result_json.setdefault("source", {})
            result_json["source"]["transcriptionProvider"] = self.transcription_provider.last_provider_name
            result_json["source"]["transcriptionModel"] = self.transcription_provider.last_provider_model
            if getattr(self.transcription_provider, "last_voice_metadata", None):
                result_json["source"]["voiceMetadata"] = self.transcription_provider.last_voice_metadata
                _append_voice_quality_warnings(result_json, self.transcription_provider.last_voice_metadata)
            if transcript_guardrail:
                _append_guardrail_metadata(result_json, "transcript", transcript_guardrail)
            self._validate_result_json(result_json)
            result = self.results.upsert(
                workspace_id=meeting.workspace_id,
                meeting_id=meeting.id,
                processing_job_id=job.id,
                schema_version=SCHEMA_VERSION,
                provider_name=self.analysis_provider.last_provider_name,
                provider_model=self.analysis_provider.last_provider_model,
                result_json=result_json,
            )
            self.segment_records.replace_for_result(
                workspace_id=meeting.workspace_id,
                meeting_id=meeting.id,
                intelligence_result_id=result.id,
                segments=result_json["transcript"]["segments"],
            )
            self.insight_records.replace_for_result(
                workspace_id=meeting.workspace_id,
                meeting_id=meeting.id,
                intelligence_result_id=result.id,
                insights=_extract_indexed_insights(result_json),
            )
            retrieval_chunks = self.retrieval_index.rebuild_for_result(result)
            job.payload = {
                **(job.payload or {}),
                "providerMetadata": {
                    "schemaVersion": SCHEMA_VERSION,
                    "transcriptionProvider": self.transcription_provider.last_provider_name,
                    "transcriptionModel": self.transcription_provider.last_provider_model,
                    "voiceMetadata": getattr(self.transcription_provider, "last_voice_metadata", {}),
                    "guardrails": {"transcript": transcript_guardrail} if transcript_guardrail else {},
                    "analysisProvider": self.analysis_provider.last_provider_name,
                    "analysisModel": self.analysis_provider.last_provider_model,
                },
                "retrievalMetadata": {
                    "chunkCount": len(retrieval_chunks),
                    "embeddingProvider": self.retrieval_index.embedding_provider.provider_name,
                    "embeddingModel": self.retrieval_index.embedding_provider.model_name,
                    "vectorIndex": self.retrieval_index.last_vector_metadata,
                },
            }
            self.jobs.update_status(job, ProcessingJobStatus.SUCCEEDED)
            self.meetings.update_status(meeting, MeetingStatus.READY)
            self.session.commit()
            return {"job_id": job.id, "meeting_id": meeting.id, "status": "succeeded"}
        except Exception as exc:
            safe_reason = "Meeting processing failed. Please retry later."
            self.jobs.update_status(
                job,
                ProcessingJobStatus.FAILED,
                safe_failure_reason=safe_reason,
                internal_error=repr(exc),
            )
            self.meetings.update_status(meeting, MeetingStatus.FAILED, safe_reason)
            self.session.commit()
            return {"job_id": job.id, "meeting_id": meeting.id, "status": "failed"}

    def _check_transcript_guardrail(self, *, meeting_id: str, transcript_segments: list) -> dict:
        if not self.settings.guardrail_transcript_enabled:
            return {}
        transcript_text = "\n".join(
            segment.text
            for segment in transcript_segments
            if getattr(segment, "text", "").strip()
        )
        result = safe_guardrail_check(
            self.guardrail_provider,
            kind="transcript",
            text=transcript_text,
            strict_mode=self.settings.guardrail_strict_mode,
            metadata={"meetingId": meeting_id, "source": "transcript"},
        )
        metadata = result.to_metadata()
        if result.action == "block" and not self.settings.guardrail_strict_mode:
            metadata["action"] = "warn"
            metadata["categories"] = list(dict.fromkeys([*metadata.get("categories", []), "non_strict_block_downgraded"]))
        return metadata

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


def _append_guardrail_metadata(result_json: dict, scope: str, guardrail_metadata: dict) -> None:
    source = result_json.setdefault("source", {})
    guardrails = source.setdefault("guardrails", {})
    guardrails[scope] = guardrail_metadata

    quality = result_json.setdefault("quality", {})
    warnings = quality.setdefault("warnings", [])
    if not isinstance(warnings, list):
        warnings = []
    action = guardrail_metadata.get("action")
    categories = guardrail_metadata.get("categories", [])
    if action in {"warn", "redact", "block"}:
        category_text = ", ".join(categories) if categories else "uncategorized"
        warnings.append(f"Guardrail {scope} check returned {action}: {category_text}.")
    quality["warnings"] = list(dict.fromkeys(warnings))
