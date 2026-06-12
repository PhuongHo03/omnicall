import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Protocol

from backend.configs.settings import Settings, get_settings
from backend.models.meeting_models import Meeting, MeetingAsset
from backend.providers.llm_provider import LLMProvider, LLMProviderError, get_llm_provider
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


class LocalAnalysisProvider:
    provider_name = "local-placeholder-analysis"
    provider_model = "deterministic-v1"
    last_provider_name = provider_name
    last_provider_model = provider_model

    def build_result(
        self,
        *,
        meeting: Meeting,
        asset: MeetingAsset,
        transcript_segments: list[TranscriptSegment],
    ) -> dict:
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
        citations = _build_citations(transcript_segments)
        default_citation_ids = [citations[0]["id"]] if citations else []
        participants = _extract_participants(transcript_segments)
        extracted = _extract_structured_sections(transcript_segments)
        empty_sections = {
            section: "No explicit evidence was found in the transcript."
            for section, values in extracted.items()
            if isinstance(values, list) and not values
        }
        executive_summary = _build_executive_summary(transcript_segments, extracted)

        return {
            "schemaVersion": SCHEMA_VERSION,
            "meeting": {
                "id": meeting.id,
                "title": meeting.title,
                "language": meeting.language,
                "startedAt": None,
                "durationSeconds": None,
            },
            "source": {
                "assetIds": [asset.id],
                "assetObjectKeys": [asset.object_key],
                "transcriptionProvider": "local-placeholder-asr",
                "analysisProvider": self.provider_name,
                "analysisModel": self.provider_model,
                "generatedAt": datetime.now(UTC).isoformat(),
            },
            "participants": [
                {"speaker": speaker, "role": "unknown", "confidence": 0.75}
                for speaker in participants
            ],
            "transcript": {
                "segments": transcript,
                "coverage": {
                    "status": "derived",
                    "coveredAssetIds": [asset.id],
                    "warning": "Audio ASR is not connected yet when the source is not a text transcript.",
                },
            },
            "summary": {
                "executive": executive_summary,
                "detailed": [
                    {
                        "title": "Transcript-derived summary",
                        "text": _join_segment_preview(transcript_segments),
                        "citationIds": default_citation_ids,
                    }
                ],
                "keyPoints": [
                    {
                        "text": item["text"],
                        "citationIds": item["citationIds"],
                    }
                    for item in extracted["importantNotes"][:3]
                ] or [
                    {
                        "text": "A processed JSON artifact now exists for this meeting.",
                        "citationIds": default_citation_ids,
                    }
                ],
            },
            "analysis": {
                "topics": extracted["topics"],
                "decisions": extracted["decisions"],
                "actionItems": extracted["actionItems"],
                "importantNotes": extracted["importantNotes"],
                "timeline": extracted["timeline"],
                "risks": extracted["risks"],
                "blockers": extracted["blockers"],
                "dependencies": extracted["dependencies"],
                "openQuestions": extracted["openQuestions"],
                "followUps": extracted["followUps"],
                "outcomes": extracted["outcomes"],
                "requirements": extracted["requirements"],
                "constraints": extracted["constraints"],
                "assumptions": extracted["assumptions"],
                "conflicts": extracted["conflicts"],
                "metrics": extracted["metrics"],
                "parkingLot": extracted["parkingLot"],
                "entities": extracted["entities"] + [
                    {"name": asset.file_name, "type": "meeting_asset", "citationIds": default_citation_ids}
                ],
                "glossary": extracted["glossary"],
                "importantQuotes": extracted["importantQuotes"],
                "emptySections": empty_sections,
            },
            "citations": citations,
            "quality": {
                "coverage": "derived",
                "warnings": [
                    "Local deterministic extraction is rule-based and should be reprocessed with LLM analysis for production use.",
                    "Sections with no evidence are represented as empty with an explicit reason.",
                ],
                "confidence": 0.7 if transcript_segments else 0.0,
            },
        }


class LLMAnalysisProvider:
    provider_name = "llm-analysis"

    def __init__(self, llm_provider: LLMProvider, fallback_provider: LocalAnalysisProvider | None = None) -> None:
        self.llm_provider = llm_provider
        self.fallback_provider = fallback_provider or LocalAnalysisProvider()
        self.provider_model = llm_provider.model_name
        self.last_provider_name = self.provider_name
        self.last_provider_model = self.provider_model

    def build_result(
        self,
        *,
        meeting: Meeting,
        asset: MeetingAsset,
        transcript_segments: list[TranscriptSegment],
    ) -> dict:
        baseline = self.fallback_provider.build_result(
            meeting=meeting,
            asset=asset,
            transcript_segments=transcript_segments,
        )
        try:
            generated = self.llm_provider.generate_json(
                system_prompt=_build_system_prompt(),
                user_prompt=_build_user_prompt(meeting, asset, transcript_segments),
            )
            result = _merge_llm_result(
                baseline=baseline,
                generated=generated,
                llm_provider=self.llm_provider,
            )
            self.last_provider_name = self.provider_name
            self.last_provider_model = self.llm_provider.model_name
            return result
        except (LLMProviderError, ValueError, KeyError, TypeError) as exc:
            result = deepcopy(baseline)
            result["source"]["analysisProvider"] = self.fallback_provider.provider_name
            result["source"]["analysisModel"] = self.fallback_provider.provider_model
            result["source"]["analysisFallbackReason"] = "LLM analysis failed; deterministic fallback was used."
            result["quality"]["warnings"].append(
                "LLM analysis was unavailable or invalid, so deterministic fallback analysis was used."
            )
            result["quality"]["llmError"] = str(exc)
            self.last_provider_name = self.fallback_provider.provider_name
            self.last_provider_model = self.fallback_provider.provider_model
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


def _extract_participants(transcript_segments: list[TranscriptSegment]) -> list[str]:
    speakers = []
    for segment in transcript_segments:
        if segment.speaker and segment.speaker not in speakers:
            speakers.append(segment.speaker)
    return speakers or ["Speaker 1"]


def _extract_structured_sections(transcript_segments: list[TranscriptSegment]) -> dict[str, list]:
    sections: dict[str, list] = {
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
    }
    for index, segment in enumerate(transcript_segments, start=1):
        text = segment.text.strip()
        lowered = text.lower()
        citation_ids = [f"cite-{index:03d}"]
        source = {"citationIds": citation_ids, "sourceSegmentIds": [segment.id], "confidence": segment.confidence}
        if not text:
            continue

        sections["topics"].append(
            {
                "title": _topic_title(text),
                "summary": text,
                **source,
            }
        )
        if _contains_any(lowered, ["decide", "decision", "agreed", "approved", "chốt", "quyết định", "thống nhất"]):
            sections["decisions"].append(
                {
                    "text": text,
                    "owner": segment.speaker,
                    "confidence": 0.75,
                    **source,
                }
            )
            sections["outcomes"].append({"text": text, **source})
        if _contains_any(lowered, ["action item", "todo", "follow up", "cần làm", "phải làm", "assign", "owner", "next step"]):
            sections["actionItems"].append(
                {
                    "owner": segment.speaker,
                    "task": _strip_leading_label(text),
                    "dueDate": _extract_due_date(text),
                    "priority": "normal",
                    "status": "open",
                    **source,
                }
            )
        if _contains_any(lowered, ["risk", "rủi ro", "concern", "uncertain", "không chắc"]):
            sections["risks"].append(
                {
                    "text": text,
                    "impact": "medium",
                    "mitigation": "Needs owner review.",
                    **source,
                }
            )
        if _contains_any(lowered, ["blocker", "blocked", "chặn", "vướng", "không thể"]):
            sections["blockers"].append({"text": text, **source})
        if _contains_any(lowered, ["depend", "dependency", "phụ thuộc", "cần từ", "waiting for"]):
            sections["dependencies"].append({"text": text, **source})
        if "?" in text or _contains_any(lowered, ["question", "câu hỏi", "chưa rõ"]):
            sections["openQuestions"].append({"question": text, **source})
        if _contains_any(lowered, ["follow up", "check lại", "xác nhận", "confirm", "next meeting"]):
            sections["followUps"].append({"text": text, "owner": segment.speaker, **source})
        if _contains_any(lowered, ["requirement", "must", "should", "yêu cầu", "cần phải"]):
            sections["requirements"].append({"text": text, **source})
        if _contains_any(lowered, ["constraint", "limited", "budget", "deadline", "giới hạn", "hạn chế"]):
            sections["constraints"].append({"text": text, **source})
        if _contains_any(lowered, ["assume", "assuming", "giả định"]):
            sections["assumptions"].append({"text": text, **source})
        if _contains_any(lowered, ["disagree", "conflict", "tradeoff", "không đồng ý", "mâu thuẫn"]):
            sections["conflicts"].append({"text": text, **source})
        if re.search(r"\b\d+(?:[.,]\d+)?\s*(?:%|percent|users?|days?|weeks?|hours?|ms|s)\b", lowered):
            sections["metrics"].append({"text": text, **source})
        if _contains_any(lowered, ["parking lot", "later", "để sau", "defer"]):
            sections["parkingLot"].append({"text": text, **source})
        if _contains_any(lowered, ["note", "important", "lưu ý", "nhớ rằng"]):
            sections["importantNotes"].append({"text": text, **source})
        elif len(sections["importantNotes"]) < 5:
            sections["importantNotes"].append({"text": text, **source})
        due_date = _extract_due_date(text)
        if due_date is not None or _contains_any(lowered, ["deadline", "milestone", "timeline", "due", "mốc", "hạn"]):
            sections["timeline"].append({"text": text, "dateText": due_date, **source})
        if 30 <= len(text) <= 220 and _contains_any(lowered, ["decide", "risk", "action", "important", "lưu ý", "quyết định"]):
            sections["importantQuotes"].append({"quote": text, **source})
        for entity in _extract_simple_entities(text):
            sections["entities"].append({"name": entity, "type": "mentioned_term", **source})

    sections["topics"] = _dedupe_by_text(sections["topics"], "summary")[:10]
    for key, values in sections.items():
        if key not in {"topics", "entities"}:
            sections[key] = _dedupe_by_text(values, "text") if values and "text" in values[0] else values
    sections["entities"] = _dedupe_by_text(sections["entities"], "name")[:20]
    return sections


def _build_executive_summary(transcript_segments: list[TranscriptSegment], extracted: dict[str, list]) -> str:
    if not transcript_segments:
        return "No transcript content was available for analysis."
    action_count = len(extracted["actionItems"])
    decision_count = len(extracted["decisions"])
    risk_count = len(extracted["risks"])
    return (
        f"Processed {len(transcript_segments)} transcript segment(s). "
        f"Detected {decision_count} decision(s), {action_count} action item(s), and {risk_count} risk item(s). "
        f"Primary discussion: {_topic_title(transcript_segments[0].text)}."
    )


def _join_segment_preview(transcript_segments: list[TranscriptSegment]) -> str:
    preview = " ".join(segment.text.strip() for segment in transcript_segments[:5] if segment.text.strip())
    return preview[:700] or "No transcript text was available."


def _topic_title(text: str) -> str:
    words = re.findall(r"[\wÀ-ỹ]+", text, flags=re.UNICODE)
    return " ".join(words[:8]) or "Meeting discussion"


def _contains_any(value: str, needles: list[str]) -> bool:
    return any(needle in value for needle in needles)


def _strip_leading_label(text: str) -> str:
    return re.sub(r"^\s*(?:action item|todo|next step|cần làm)\s*[:\-]\s*", "", text, flags=re.IGNORECASE).strip()


def _extract_due_date(text: str) -> str | None:
    match = re.search(
        r"\b(?:by|due|before|deadline|hạn|trước)\s+([A-Za-zÀ-ỹ0-9 ,./-]{2,40})",
        text,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip(" .") if match else None


def _extract_simple_entities(text: str) -> list[str]:
    entities = re.findall(r"\b[A-Z][A-Za-z0-9_-]{2,}(?:\s+[A-Z][A-Za-z0-9_-]{2,})?\b", text)
    return [entity for entity in entities if entity.lower() not in {"the", "this", "that"}]


def _dedupe_by_text(items: list[dict], key: str) -> list[dict]:
    seen = set()
    deduped = []
    for item in items:
        value = str(item.get(key) or "").lower().strip()
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(item)
    return deduped


def get_analysis_provider(settings: Settings | None = None) -> AnalysisProvider:
    resolved_settings = settings or get_settings()
    if resolved_settings.analysis_provider.strip().lower() == "llm":
        return LLMAnalysisProvider(get_llm_provider())
    return LocalAnalysisProvider()


def _build_system_prompt() -> str:
    return (
        "You are Omnicall's meeting intelligence extraction engine. "
        "Return only a valid JSON object. Do not include markdown. "
        "Extract useful meeting intelligence from the transcript while preserving evidence links. "
        "Use the provided transcript segment IDs in citationIds whenever evidence exists."
    )


def _build_user_prompt(meeting: Meeting, asset: MeetingAsset, transcript_segments: list[TranscriptSegment]) -> str:
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
    payload = {
        "requiredSchemaVersion": SCHEMA_VERSION,
        "meeting": {
            "id": meeting.id,
            "title": meeting.title,
            "language": meeting.language,
        },
        "source": {
            "assetId": asset.id,
            "assetFileName": asset.file_name,
            "assetContentType": asset.content_type,
        },
        "transcript": {"segments": transcript},
        "requiredOutputShape": {
            "participants": [],
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
                "emptySections": {},
            },
            "citations": [],
            "quality": {"coverage": "", "warnings": [], "confidence": 0.0},
        },
    }
    return (
        "Generate the meeting intelligence sections for this transcript. "
        "Every extracted item should include citationIds when evidence exists. "
        "If a section has no evidence, keep it empty and explain it in analysis.emptySections. "
        f"Input JSON: {json.dumps(payload, ensure_ascii=False)}"
    )


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
        "analysisModel": llm_provider.model_name,
        "llmProvider": llm_provider.provider_name,
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
    result.setdefault("participants", [])
    result.setdefault("summary", {})
    result["summary"].setdefault("executive", "")
    result["summary"].setdefault("detailed", [])
    result["summary"].setdefault("keyPoints", [])
    result.setdefault("analysis", {})
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
    result.setdefault("citations", [])
    result.setdefault("quality", {})
    result["quality"].setdefault("coverage", "partial")
    result["quality"].setdefault("warnings", [])
    result["quality"].setdefault("confidence", 0.5)
