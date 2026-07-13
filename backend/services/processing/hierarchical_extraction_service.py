import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from backend.repositories.transcript_window_repository import TranscriptWindowRepository
from backend.repositories.meeting_repository import MeetingAssetRepository, MeetingIntelligenceResultRepository, MeetingRepository
from backend.providers.transcript_types import TranscriptSegment
from backend.services.processing.intelligence_reducer import reduce_window_results
from backend.services.processing.transcript_window_service import TranscriptWindowService


@dataclass(frozen=True)
class HierarchicalExtractionResult:
    result_json: dict
    generation: str
    window_count: int
    duration_ms: int


class HierarchicalExtractionService:
    """Orchestrates bounded local extraction and global reduction."""

    def __init__(self, *, session, analysis_provider, window_repository=None, window_service=None, settings=None) -> None:
        self.session = session
        self.analysis_provider = analysis_provider
        self.windows = window_repository or TranscriptWindowRepository(session)
        if window_service is not None:
            self.window_service = window_service
        else:
            self.window_service = TranscriptWindowService(
                target_tokens=getattr(settings, "extraction_window_target_tokens", 2000),
                hard_limit_tokens=getattr(settings, "extraction_window_hard_limit_tokens", 2800),
                overlap_segments=getattr(settings, "extraction_window_overlap_segments", 1),
            )
        self.max_workers = max(1, min(8, getattr(settings, "extraction_window_max_workers", 4)))

    def run(self, *, meeting, asset, transcript_segments: list, detected_language: str | None = None) -> HierarchicalExtractionResult:
        generation = self._generation(transcript_segments)
        windows = self.window_service.build(transcript_segments)
        window_records = [window.as_record() for window in windows]
        records = self.windows.replace_for_generation(
            meeting_id=meeting.id,
            generation=generation,
            windows=window_records,
        )
        for record in records:
            self.windows.mark_processing(record)

        def extract(window):
            builder = getattr(self.analysis_provider, "build_window_result", None)
            if not callable(builder):
                builder = self.analysis_provider.build_result
            return builder(
                meeting=meeting,
                asset=asset,
                transcript_segments=window.segments,
                detected_language=detected_language,
            )

        local_results: list[dict] = []
        try:
            with ThreadPoolExecutor(max_workers=min(self.max_workers, len(windows) or 1)) as executor:
                local_results = list(executor.map(extract, windows))
            for record, local_result in zip(records, local_results, strict=True):
                self.windows.mark_succeeded(record, local_result)
        except Exception as exc:
            for record in records:
                if record.status == "processing":
                    self.windows.mark_failed(record, str(exc))
            raise
        canonical = reduce_window_results(
            meeting=meeting,
            asset=asset,
            transcript_segments=transcript_segments,
            windows=window_records,
            local_results=local_results,
            provider_name=getattr(self.analysis_provider, "last_provider_name", self.analysis_provider.provider_name),
            provider_model=getattr(self.analysis_provider, "last_provider_model", self.analysis_provider.provider_model),
        )
        canonical.setdefault("extraction", {})["generation"] = generation
        return HierarchicalExtractionResult(
            result_json=canonical,
            generation=generation,
            window_count=len(windows),
            duration_ms=0,
        )

    def _generation(self, segments: list) -> str:
        payload = [
            {"id": segment.id, "startMs": segment.start_ms, "endMs": segment.end_ms, "text": segment.text}
            for segment in segments
        ]
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:48]

    def extract_window_for_task(self, *, meeting_id: str, generation: str, window_id: str) -> dict:
        meetings = MeetingRepository(self.session)
        results = MeetingIntelligenceResultRepository(self.session)
        assets = MeetingAssetRepository(self.session)
        meeting = meetings.get(meeting_id)
        result = results.get_latest_for_meeting(meeting_id)
        asset = assets.get_latest_for_meeting(meeting_id)
        window = self.windows.get(meeting_id=meeting_id, generation=generation, window_id=window_id)
        if meeting is None or result is None or asset is None or window is None:
            raise ValueError("Extraction window task references missing meeting state.")
        segments_by_id = {
            item.get("id"): TranscriptSegment(
                id=item.get("id"),
                speaker=item.get("speaker") or item.get("speakerLabel") or "",
                start_ms=item.get("startMs") or 0,
                end_ms=item.get("endMs") or 0,
                text=item.get("text") or "",
                confidence=float(item.get("confidence") or 0),
            )
            for item in result.result_json.get("transcript", {}).get("segments", [])
            if isinstance(item, dict) and item.get("id")
        }
        segments = [segments_by_id[segment_id] for segment_id in window.segment_ids if segment_id in segments_by_id]
        self.windows.mark_processing(window)
        builder = getattr(self.analysis_provider, "build_window_result", None) or self.analysis_provider.build_result
        local_result = builder(meeting=meeting, asset=asset, transcript_segments=segments)
        self.windows.mark_succeeded(window, local_result)
        return {"meetingId": meeting_id, "generation": generation, "windowId": window_id, "status": "succeeded"}
