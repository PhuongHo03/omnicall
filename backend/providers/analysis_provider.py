import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Protocol

from backend.configs.settings import Settings, get_settings
from backend.models.meeting_models import Meeting, MeetingAsset
from backend.providers.llm_provider import (
    LLMProvider,
    get_configured_primary_model_name,
    get_effective_model_name,
    get_effective_provider_name,
    get_llm_provider,
)
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
    ) -> dict:
        ...


class LLMAnalysisProvider:
    provider_name = "llm-analysis"

    def __init__(self, llm_provider: LLMProvider) -> None:
        self.llm_provider = llm_provider
        self.provider_model = get_configured_primary_model_name(llm_provider)
        self.last_provider_name = self.provider_name
        self.last_provider_model = self.provider_model

    def build_result(
        self,
        *,
        meeting: Meeting,
        asset: MeetingAsset,
        transcript_segments: list[TranscriptSegment],
    ) -> dict:
        baseline = _build_base_result(
            meeting=meeting,
            asset=asset,
            transcript_segments=transcript_segments,
        )
        generated = self.llm_provider.generate_json(
            system_prompt=_build_system_prompt(),
            user_prompt=_build_user_prompt(meeting, asset, transcript_segments),
        )
        if not _has_meeting_intelligence(generated):
            generated = self.llm_provider.generate_json(
                system_prompt=_build_system_prompt(),
                user_prompt=_build_repair_prompt(
                    meeting=meeting,
                    asset=asset,
                    transcript_segments=transcript_segments,
                    invalid_response=generated,
                ),
            )
        result = _merge_llm_result(
            baseline=baseline,
            generated=generated,
            llm_provider=self.llm_provider,
        )
        self.last_provider_name = self.provider_name
        self.last_provider_model = get_effective_model_name(self.llm_provider)
        return result


def _build_citations(transcript_segments: list[TranscriptSegment]) -> list[dict]:
    return [
        {
            "id": f"cite-{index:03d}",
            "segmentIds": [segment.id],
            "startMs": segment.start_ms,
            "endMs": segment.end_ms,
        }
        for index, segment in enumerate(transcript_segments, start=1)
    ]


def _build_base_result(*, meeting: Meeting, asset: MeetingAsset, transcript_segments: list[TranscriptSegment]) -> dict:
    transcript = [
        {
            "id": segment.id,
            "speaker": segment.speaker,
            "startMs": segment.start_ms,
            "endMs": segment.end_ms,
            "text": segment.text,
            "confidence": segment.confidence,
        }
        for segment in transcript_segments
    ]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "meeting": {
            "id": meeting.id,
            "title": meeting.title,
            "startedAt": None,
            "durationSeconds": None,
        },
        "source": {
            "assetIds": [asset.id],
            "assetObjectKeys": [asset.object_key],
            "analysisProvider": "llm-analysis",
            "analysisModel": "",
            "generatedAt": datetime.now(UTC).isoformat(),
        },
        "participants": [],
        "transcript": {
            "segments": transcript,
            "coverage": {
                "status": "model-derived",
                "coveredAssetIds": [asset.id],
            },
        },
        "summary": {"executive": "", "detailed": [], "keyPoints": []},
        "analysis": {
            "topics": [],
            "decisions": [],
            "actionItems": [],
            "importantNotes": [],
            "timeline": [],
            "risks": [],
            "blockers": [],
            "dependencies": [],
            "openQuestions": [],
            "followUps": [],
            "outcomes": [],
            "requirements": [],
            "constraints": [],
            "assumptions": [],
            "conflicts": [],
            "metrics": [],
            "parkingLot": [],
            "entities": [],
            "glossary": [],
            "importantQuotes": [],
            "emptySections": {},
        },
        "citations": _build_citations(transcript_segments),
        "quality": {"coverage": "partial", "warnings": [], "confidence": 0.5},
    }


def get_analysis_provider(settings: Settings | None = None) -> AnalysisProvider:
    return LLMAnalysisProvider(get_llm_provider())


def _build_system_prompt() -> str:
    return (
        "You are Omnicall's meeting intelligence extraction engine. "
        "Return only a valid JSON object with meeting intelligence. Do not include markdown. "
        "Extract useful meeting intelligence from the transcript while preserving evidence links. "
        "Use the provided transcript segment IDs in citationIds whenever evidence exists. "
        "Do not echo the input, required output shape, transcript wrapper, or instructions."
    )


def _build_user_prompt(meeting: Meeting, asset: MeetingAsset, transcript_segments: list[TranscriptSegment]) -> str:
    transcript = _build_prompt_transcript(transcript_segments)
    payload = _prompt_payload(meeting=meeting, asset=asset)
    return (
        "Generate the output JSON for this meeting transcript.\n"
        "Required top-level keys: participants, summary, analysis, citations, quality.\n"
        "Required summary keys: executive, detailed, keyPoints. summary.executive must be a non-empty string.\n"
        "Required analysis keys: topics, decisions, actionItems, importantNotes, timeline, risks, blockers, "
        "dependencies, openQuestions, followUps, outcomes, requirements, constraints, assumptions, conflicts, "
        "metrics, parkingLot, entities, glossary, importantQuotes, emptySections.\n"
        "Each extracted item should include citationIds using transcript segment ids such as seg-001 when evidence exists.\n"
        "If a section has no evidence, return an empty array and explain it in analysis.emptySections.\n"
        "Do not return requiredSchemaVersion, requiredOutputShape, source, transcript, or meeting as top-level keys.\n"
        f"Meeting metadata JSON: {json.dumps(payload, ensure_ascii=False)}\n"
        "Transcript line format: segmentId|speaker|text\n"
        f"Transcript lines:\n{transcript}"
    )


def _build_repair_prompt(
    *,
    meeting: Meeting,
    asset: MeetingAsset,
    transcript_segments: list[TranscriptSegment],
    invalid_response: dict,
) -> str:
    transcript = _build_prompt_transcript(transcript_segments)
    payload = _prompt_payload(meeting=meeting, asset=asset)
    invalid_keys = list(invalid_response.keys())[:12]
    return (
        "Your previous JSON was invalid for Omnicall because it did not contain real meeting intelligence. "
        f"It had these top-level keys: {json.dumps(invalid_keys, ensure_ascii=False)}.\n"
        "Return a corrected JSON object only. Do not echo the input.\n"
        "The corrected JSON must contain exactly these top-level sections: participants, summary, analysis, citations, quality.\n"
        "summary.executive must be a concise non-empty Vietnamese executive summary of the meeting.\n"
        "Extract decisions, actionItems, timeline, risks, dependencies, openQuestions, and keyPoints from the transcript.\n"
        "Use transcript segment IDs in citationIds when evidence exists.\n"
        f"Meeting metadata JSON: {json.dumps(payload, ensure_ascii=False)}\n"
        "Transcript line format: segmentId|speaker|text\n"
        f"Transcript lines:\n{transcript}"
    )


def _prompt_payload(*, meeting: Meeting, asset: MeetingAsset) -> dict:
    return {
        "meeting": {
            "id": meeting.id,
            "title": meeting.title,
        },
        "asset": {
            "id": asset.id,
            "fileName": asset.file_name,
            "contentType": asset.content_type,
        },
    }


def _build_prompt_transcript(transcript_segments: list[TranscriptSegment]) -> str:
    return "\n".join(
        f"{segment.id}|{_sanitize_transcript_field(segment.speaker)}|{_sanitize_transcript_field(segment.text)}"
        for segment in transcript_segments
    )


def _sanitize_transcript_field(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).replace("|", "/").strip()


def _has_meeting_intelligence(generated: dict) -> bool:
    summary = generated.get("summary")
    analysis = generated.get("analysis")
    if not isinstance(summary, dict) or not isinstance(analysis, dict):
        return False
    executive = summary.get("executive")
    if not isinstance(executive, str) or not executive.strip():
        return False
    return any(
        isinstance(analysis.get(key), list) and analysis[key]
        for key in ("decisions", "actionItems", "timeline", "risks", "importantNotes", "keyPoints")
    ) or bool(summary.get("keyPoints"))


def _normalize_citation_ids(data: Any, segment_to_cite: dict[str, str], valid_cite_ids: set[str]) -> None:
    if isinstance(data, dict):
        if "citationIds" in data and isinstance(data["citationIds"], list):
            normalized = []
            for cid in data["citationIds"]:
                if isinstance(cid, str):
                    if cid in valid_cite_ids:
                        normalized.append(cid)
                    elif cid in segment_to_cite:
                        normalized.append(segment_to_cite[cid])
                    elif cid.replace("seg-", "cite-") in valid_cite_ids:
                        normalized.append(cid.replace("seg-", "cite-"))
            data["citationIds"] = normalized
        for val in data.values():
            _normalize_citation_ids(val, segment_to_cite, valid_cite_ids)
    elif isinstance(data, list):
        for val in data:
            _normalize_citation_ids(val, segment_to_cite, valid_cite_ids)


def _merge_llm_result(*, baseline: dict, generated: dict, llm_provider: LLMProvider) -> dict:
    result = deepcopy(baseline)
    for section in ("participants", "summary", "analysis", "citations", "quality"):
        if section in generated:
            result[section] = generated[section]

    result["schemaVersion"] = SCHEMA_VERSION
    result["meeting"] = baseline["meeting"]
    result["source"] = {
        **baseline["source"],
        "analysisProvider": "llm-analysis",
        "analysisModel": get_effective_model_name(llm_provider),
        "llmProvider": get_effective_provider_name(llm_provider),
        "generatedAt": datetime.now(UTC).isoformat(),
    }
    result["transcript"] = baseline["transcript"]

    if not result.get("citations"):
        result["citations"] = baseline["citations"]

    _ensure_result_defaults(result)

    segment_to_cite = {}
    valid_cite_ids = set()
    for citation in result.get("citations", []):
        cite_id = citation.get("id")
        if cite_id:
            valid_cite_ids.add(cite_id)
            for seg_id in citation.get("segmentIds", []):
                segment_to_cite[seg_id] = cite_id

    _normalize_citation_ids(result, segment_to_cite, valid_cite_ids)

    return result


def _ensure_result_defaults(result: dict) -> None:
    if not isinstance(result.get("participants"), list):
        result["participants"] = []
    if isinstance(result.get("summary"), str):
        result["summary"] = {"executive": result["summary"]}
    elif not isinstance(result.get("summary"), dict):
        result["summary"] = {}
    result["summary"].setdefault("executive", "")
    result["summary"].setdefault("detailed", [])
    result["summary"].setdefault("keyPoints", [])
    if not isinstance(result.get("analysis"), dict):
        result["analysis"] = {}
    for key in (
        "topics",
        "decisions",
        "actionItems",
        "importantNotes",
        "timeline",
        "risks",
        "blockers",
        "dependencies",
        "openQuestions",
        "followUps",
        "outcomes",
        "requirements",
        "constraints",
        "assumptions",
        "conflicts",
        "metrics",
        "parkingLot",
        "entities",
        "glossary",
        "importantQuotes",
    ):
        result["analysis"].setdefault(key, [])
    result["analysis"].setdefault("emptySections", {})
    if not isinstance(result.get("citations"), list):
        result["citations"] = []
    if not isinstance(result.get("quality"), dict):
        result["quality"] = {}
    result["quality"].setdefault("coverage", "partial")
    result["quality"].setdefault("warnings", [])
    result["quality"].setdefault("confidence", 0.5)
