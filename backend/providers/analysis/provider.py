import json
import re
import unicodedata
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from backend.configs.settings import Settings, get_settings
from backend.models.meeting_models import Meeting, MeetingAsset
from backend.providers.llm import (
    LLMProvider,
    get_configured_primary_model_name,
    get_effective_model_name,
    get_effective_provider_name,
    get_llm_provider,
)
from backend.providers.transcript_types import TranscriptSegment
from backend.providers.contracts.analysis import AnalysisProvider, ANALYSIS_CANDIDATE_SCHEMA_VERSION


_WINDOW_PARTICIPANT_COUNT_ID = "derived-window-participant-count"
_IGNORED_SPEAKER_LABELS = frozenset(
    {
        "background",
        "background noise",
        "crosstalk",
        "n a",
        "na",
        "noise",
        "none",
        "null",
        "other",
        "overlap",
        "silence",
        "speaker unknown",
        "unk",
        "unassigned",
        "unidentified",
        "unknown",
        "unknown speaker",
    }
)


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
        detected_language: str | None = None,
    ) -> dict:
        baseline = _build_base_result(
            meeting=meeting,
            asset=asset,
            transcript_segments=transcript_segments,
        )
        generated = _generate_analysis_json(
            llm_provider=self.llm_provider,
            primary_system_prompt=_build_system_prompt(),
            primary_user_prompt=_build_user_prompt(meeting, asset, transcript_segments),
            fallback_system_prompt=_build_compact_system_prompt(),
            fallback_user_prompt=_build_compact_user_prompt(meeting, asset, transcript_segments),
        )
        if not _has_meeting_intelligence(generated):
            generated = _generate_analysis_json(
                llm_provider=self.llm_provider,
                primary_system_prompt=_build_system_prompt(),
                primary_user_prompt=_build_repair_prompt(
                    meeting=meeting,
                    asset=asset,
                    transcript_segments=transcript_segments,
                    invalid_response=generated,
                    detected_language=detected_language,
                ),
                fallback_system_prompt=_build_compact_system_prompt(),
                fallback_user_prompt=_build_compact_user_prompt(
                    meeting,
                    asset,
                    transcript_segments,
                    detected_language=detected_language,
                    repair=True,
                ),
            )
        result = _merge_llm_result(
            baseline=baseline,
            generated=generated,
            llm_provider=self.llm_provider,
        )
        self.last_provider_name = get_effective_provider_name(self.llm_provider)
        self.last_provider_model = get_effective_model_name(self.llm_provider)
        return result

    def build_window_result(
        self,
        *,
        meeting: Meeting,
        asset: MeetingAsset,
        transcript_segments: list[TranscriptSegment],
        detected_language: str | None = None,
    ) -> dict:
        """Extract one bounded window; reduction happens outside the provider."""
        return self.build_result(
            meeting=meeting,
            asset=asset,
            transcript_segments=transcript_segments,
            detected_language=detected_language,
        )


def _build_citations(transcript_segments: list[TranscriptSegment]) -> list[dict]:
    return [
        {
            "id": f"cite-{index:03d}",
            "segmentIds": [segment.id],
            "startMs": segment.start_ms,
            "endMs": segment.end_ms,
            "speakerLabels": [segment.speaker] if segment.speaker else [],
            "quote": segment.text,
            "evidenceType": "direct_quote",
        }
        for index, segment in enumerate(transcript_segments, start=1)
    ]


def _build_base_result(*, meeting: Meeting, asset: MeetingAsset, transcript_segments: list[TranscriptSegment]) -> dict:
    transcript = [
        {
            "id": segment.id,
            "speakerLabel": segment.speaker,
            "speaker": segment.speaker,
            "startMs": segment.start_ms,
            "endMs": segment.end_ms,
            "text": segment.text,
            "confidence": segment.confidence,
        }
        for segment in transcript_segments
    ]
    return {
        "schemaVersion": ANALYSIS_CANDIDATE_SCHEMA_VERSION,
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
        "evidence": {
            "citations": _build_citations(transcript_segments),
        },
        "speakers": _build_speaker_stats(transcript_segments),
        "participants": [],
        "entities": [],
        "facts": [],
        "events": [],
        "relationships": [],
        "topics": [],
        "summaries": {"executive": {"text": "", "topicIds": [], "citationIds": []}, "topicLevel": [], "timelineLevel": []},
        "actions": [],
        "decisions": [],
        "risks": [],
        "questions": [],
        "transcript": {
            "segments": transcript,
            "coverage": {
                "status": "model-derived",
                "coveredAssetIds": [asset.id],
            },
        },
        "quality": {"coverage": "partial", "warnings": [], "confidence": 0.5},
        "extraction": {
            "overallConfidence": 0.5,
            "method": "llm_with_deterministic_verification",
            "unsupportedClaims": [],
            "warnings": [],
        },
    }


def _build_speaker_stats(transcript_segments: list[TranscriptSegment]) -> dict:
    speakers: dict[str, dict] = {}
    for segment in transcript_segments:
        label = _speaker_label(segment.speaker)
        entry = speakers.setdefault(
            label,
            {
                "label": label,
                "segmentCount": 0,
                "totalTalkTimeMs": 0,
                "mappedParticipantId": None,
                "confidence": 0.0,
                "countsTowardParticipantCount": _is_countable_speaker_label(label),
            },
        )
        entry["segmentCount"] += 1
        if isinstance(segment.start_ms, int) and isinstance(segment.end_ms, int):
            entry["totalTalkTimeMs"] += max(0, segment.end_ms - segment.start_ms)
        if isinstance(segment.confidence, int | float):
            current = entry.get("_confidenceTotal", 0.0)
            entry["_confidenceTotal"] = current + float(segment.confidence)
    items = []
    for entry in speakers.values():
        total = entry.pop("_confidenceTotal", None)
        if isinstance(total, int | float) and entry["segmentCount"]:
            entry["confidence"] = round(total / entry["segmentCount"], 4)
        items.append(entry)
    items.sort(key=lambda item: str(item["label"]))
    counted_items = [item for item in items if item["countsTowardParticipantCount"]]
    ignored_items = [item for item in items if not item["countsTowardParticipantCount"]]
    return {
        "speakerCount": len(counted_items),
        "identifiedParticipantCount": 0,
        "mentionedOnlyCount": 0,
        "ignoredSpeakerLabelCount": len(ignored_items),
        "ignoredSegmentCount": sum(int(item["segmentCount"]) for item in ignored_items),
        "items": items,
    }


def _speaker_label(value: object) -> str:
    label = re.sub(r"\s+", " ", str(value or "")).strip()
    return label or "Unknown"


def _is_countable_speaker_label(value: object) -> bool:
    normalized = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.casefold()).strip()
    if not normalized or normalized in _IGNORED_SPEAKER_LABELS:
        return False
    return not bool(
        re.fullmatch(
            r"(?:background(?: noise)?|crosstalk|noise|silence|overlap|unk|unknown|unassigned|unidentified)(?: \d+)?",
            normalized,
        )
    )


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


def _generate_analysis_json(
    *,
    llm_provider: LLMProvider,
    primary_system_prompt: str,
    primary_user_prompt: str,
    fallback_system_prompt: str,
    fallback_user_prompt: str,
) -> dict:
    """Use the full contract on the primary and a bounded contract locally."""
    generate_with_fallback = getattr(llm_provider, "generate_json_with_fallback_prompts", None)
    if callable(generate_with_fallback):
        return generate_with_fallback(
            system_prompt=primary_system_prompt,
            user_prompt=primary_user_prompt,
            fallback_system_prompt=fallback_system_prompt,
            fallback_user_prompt=fallback_user_prompt,
        )
    return llm_provider.generate_json(
        system_prompt=primary_system_prompt,
        user_prompt=primary_user_prompt,
    )


def _build_compact_system_prompt() -> str:
    return (
        "Extract meeting intelligence. Return one valid JSON object only, without markdown. "
        "Use transcript segment IDs in citationIds and do not invent unsupported details."
    )


def _build_compact_user_prompt(
    meeting: Meeting,
    asset: MeetingAsset,
    transcript_segments: list[TranscriptSegment],
    *,
    detected_language: str | None = None,
    repair: bool = False,
) -> str:
    transcript = _build_prompt_transcript(transcript_segments)
    language_name = _language_code_to_name(detected_language or "vi")
    repair_instruction = "The previous response was incomplete. " if repair else ""
    return (
        f"{repair_instruction}Summarize this transcript in {language_name}. "
        "Return only supported keys from: summaries, participants, facts, topics, actions, decisions, risks, questions. "
        "summaries.executive must be {text, topicIds, citationIds} with non-empty text. "
        "Each list must contain at most one very short item; omit empty lists and keep at most four list items total. "
        "Every supported item must have id and citationIds using segment IDs; include confidence only when it is essential. "
        "Do not include explanations, duplicated evidence, or optional fields. "
        "Omit unknown fields and unsupported items.\n"
        f"Meeting: {json.dumps(_prompt_payload(meeting=meeting, asset=asset), ensure_ascii=False)}\n"
        "Lines are segmentId|speaker|startMs|endMs|confidence|text\n"
        f"{transcript}"
    )


def _build_user_prompt(meeting: Meeting, asset: MeetingAsset, transcript_segments: list[TranscriptSegment]) -> str:
    transcript = _build_prompt_transcript(transcript_segments)
    payload = _prompt_payload(meeting=meeting, asset=asset)
    return (
        "Generate candidate meeting intelligence JSON for this transcript. Return only fields you can infer from evidence.\n"
        "Allowed top-level keys: participants, entities, facts, events, relationships, topics, summaries, actions, decisions, risks, questions, quality, extraction.\n"
        "Do not return schemaVersion, meeting, source, transcript, evidence, speakers, requiredSchemaVersion, or requiredOutputShape.\n"
        "Use citationIds with transcript segment IDs such as seg-001 or canonical citation IDs such as cite-001 when evidence exists.\n"
        "Use stable ids with prefixes: participant-, entity-, fact-, event-, rel-, topic-, action-, decision-, risk-, question-.\n"
        "Participants must distinguish isAttendee from isMentionedOnly. Facts must be atomic. Events must include type/title/status when available.\n"
        "Actions, decisions, risks, questions, facts, events, entities, relationships, topics, and summaries should include confidence and citationIds when supported.\n"
        "Every relationship must include both from and to endpoint objects with type and id. Omit a relationship when either endpoint cannot be identified.\n"
        "summaries.executive must be an object with text, topicIds, and citationIds; text must be non-empty.\n"
        f"Meeting metadata JSON: {json.dumps(payload, ensure_ascii=False)}\n"
        "Transcript line format: segmentId|speaker|startMs|endMs|confidence|text\n"
        f"Transcript lines:\n{transcript}"
    )


def _build_repair_prompt(
    *,
    meeting: Meeting,
    asset: MeetingAsset,
    transcript_segments: list[TranscriptSegment],
    invalid_response: dict,
    detected_language: str | None = None,
) -> str:
    transcript = _build_prompt_transcript(transcript_segments)
    payload = _prompt_payload(meeting=meeting, asset=asset)
    invalid_keys = list(invalid_response.keys())[:12]
    language_name = _language_code_to_name(detected_language or "vi")
    return (
        "Your previous JSON was invalid for Omnicall because it did not contain real meeting intelligence. "
        f"It had these top-level keys: {json.dumps(invalid_keys, ensure_ascii=False)}.\n"
        "Return a corrected JSON object only. Do not echo the input.\n"
        "The corrected JSON may contain only: participants, entities, facts, events, relationships, topics, summaries, actions, decisions, risks, questions, quality, extraction.\n"
        f"summaries.executive.text must be a concise non-empty {language_name} executive summary of the meeting.\n"
        "Extract precise participants, facts, events, actions, decisions, risks, open questions, entities, relationships, and topics from the transcript.\n"
        "Every relationship must include both from and to endpoint objects with type and id; omit malformed relationships.\n"
        "Use transcript segment IDs in citationIds when evidence exists.\n"
        f"Meeting metadata JSON: {json.dumps(payload, ensure_ascii=False)}\n"
        "Transcript line format: segmentId|speaker|startMs|endMs|confidence|text\n"
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
        f"{segment.id}|{_sanitize_transcript_field(segment.speaker)}|{segment.start_ms}|{segment.end_ms}|{segment.confidence}|{_sanitize_transcript_field(segment.text)}"
        for segment in transcript_segments
    )


def _sanitize_transcript_field(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "")).replace("|", "/").strip()


def _language_code_to_name(language_code: str | None) -> str:
    """Convert ISO language code to English name."""
    if not language_code:
        return "Vietnamese"
    mapping = {
        "vi": "Vietnamese",
        "en": "English",
        "ja": "Japanese",
        "zh": "Chinese",
        "ko": "Korean",
        "fr": "French",
        "es": "Spanish",
        "de": "German",
        "pt": "Portuguese",
        "ru": "Russian",
        "th": "Thai",
    }
    return mapping.get(language_code.lower(), "English")


def _has_meeting_intelligence(generated: dict) -> bool:
    summaries = generated.get("summaries")
    executive_obj = summaries.get("executive") if isinstance(summaries, dict) else None
    executive = executive_obj.get("text") if isinstance(executive_obj, dict) else None
    # A bounded local fallback may deliberately return only a cited executive
    # summary. The reducer still retains the authoritative transcript and
    # deterministic speaker/count facts, so forcing a second full LLM call
    # merely to add an optional record wastes the fallback budget.
    if isinstance(executive, str) and executive.strip():
        return True
    # The reducer can create a transcript-grounded executive summary when a
    # bounded fallback returned supported records but omitted that projection.
    # Only echo/shape-only output needs another LLM repair attempt.
    return any(
        isinstance(generated.get(key), list) and generated[key]
        for key in ("facts", "events", "actions", "decisions", "risks", "questions", "topics", "participants")
    )


def _normalize_citation_ids(data: Any, segment_to_cite: dict[str, str], valid_cite_ids: set[str]) -> set[str]:
    dropped: set[str] = set()
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
                    else:
                        dropped.add(cid)
            data["citationIds"] = normalized
        for val in data.values():
            dropped.update(_normalize_citation_ids(val, segment_to_cite, valid_cite_ids))
    elif isinstance(data, list):
        for val in data:
            dropped.update(_normalize_citation_ids(val, segment_to_cite, valid_cite_ids))
    return dropped


def _merge_llm_result(*, baseline: dict, generated: dict, llm_provider: LLMProvider) -> dict:
    result = deepcopy(baseline)
    for section in (
        "participants",
        "entities",
        "facts",
        "events",
        "relationships",
        "topics",
        "summaries",
        "actions",
        "decisions",
        "risks",
        "questions",
        "quality",
        "extraction",
    ):
        if section in generated:
            result[section] = generated[section]

    result["schemaVersion"] = ANALYSIS_CANDIDATE_SCHEMA_VERSION
    result["meeting"] = baseline["meeting"]
    result["source"] = {
        **baseline["source"],
        "analysisProvider": "llm-analysis",
        "analysisModel": get_effective_model_name(llm_provider),
        "llmProvider": get_effective_provider_name(llm_provider),
        "fallbackUsed": bool(getattr(llm_provider, "last_fallback_used", False)),
        "primaryErrorType": getattr(llm_provider, "last_primary_error_type", None),
        "primaryErrorMessage": getattr(llm_provider, "last_primary_error_message", None),
        "generatedAt": datetime.now(UTC).isoformat(),
    }
    result["transcript"] = baseline["transcript"]
    result["evidence"] = baseline["evidence"]
    result["speakers"] = baseline["speakers"]

    _ensure_result_defaults(result)

    segment_to_cite = {}
    valid_cite_ids = set()
    for citation in result.get("evidence", {}).get("citations", []):
        cite_id = citation.get("id")
        if cite_id:
            valid_cite_ids.add(cite_id)
            for seg_id in citation.get("segmentIds", []):
                segment_to_cite[seg_id] = cite_id

    dropped_citations = _normalize_citation_ids(result, segment_to_cite, valid_cite_ids)
    if dropped_citations:
        warnings = _list_at(result, "quality", "warnings")
        warnings.append(f"LLM cited {len(dropped_citations)} non-existent citation(s): {', '.join(sorted(dropped_citations))}")
        result["quality"]["warnings"] = warnings
        result["extraction"]["warnings"] = list(dict.fromkeys([*result["extraction"].get("warnings", []), *warnings]))

    _link_speakers_to_participants(result)
    _add_deterministic_facts(result)
    _normalize_relationships(result)
    _ensure_executive_summary(result)
    _mark_unsupported_claims(result)

    return result


def _ensure_result_defaults(result: dict) -> None:
    if not isinstance(result.get("evidence"), dict):
        result["evidence"] = {"citations": []}
    if not isinstance(result["evidence"].get("citations"), list):
        result["evidence"]["citations"] = []
    if not isinstance(result.get("speakers"), dict):
        result["speakers"] = {"speakerCount": 0, "identifiedParticipantCount": 0, "mentionedOnlyCount": 0, "items": []}
    result["speakers"].setdefault("speakerCount", len(result["speakers"].get("items", [])) if isinstance(result["speakers"].get("items"), list) else 0)
    result["speakers"].setdefault("identifiedParticipantCount", 0)
    result["speakers"].setdefault("mentionedOnlyCount", 0)
    result["speakers"].setdefault("items", [])
    if not isinstance(result.get("participants"), list):
        result["participants"] = []
    for index, participant in enumerate([item for item in result["participants"] if isinstance(item, dict)], start=1):
        _ensure_record_id(participant, "participant", index, aliases=("participantId",))
    for key in ("entities", "facts", "events", "relationships", "topics", "actions", "decisions", "risks", "questions"):
        if not isinstance(result.get(key), list):
            result[key] = []
        for index, item in enumerate([record for record in result[key] if isinstance(record, dict)], start=1):
            _ensure_record_id(item, _id_prefix(key), index, aliases=(f"{_id_prefix(key)}Id",))
    if not isinstance(result.get("summaries"), dict):
        result["summaries"] = {}
    executive = result["summaries"].get("executive")
    if isinstance(executive, str):
        executive = {"text": executive, "topicIds": [], "citationIds": []}
    elif not isinstance(executive, dict):
        executive = {"text": "", "topicIds": [], "citationIds": []}
    executive.setdefault("text", "")
    executive.setdefault("topicIds", [])
    executive.setdefault("citationIds", [])
    result["summaries"]["executive"] = executive
    result["summaries"].setdefault("topicLevel", [])
    result["summaries"].setdefault("timelineLevel", [])
    if not isinstance(result.get("quality"), dict):
        result["quality"] = {}
    result["quality"].setdefault("coverage", "partial")
    result["quality"].setdefault("warnings", [])
    result["quality"].setdefault("confidence", 0.5)
    if not isinstance(result.get("extraction"), dict):
        result["extraction"] = {}
    result["extraction"].setdefault("overallConfidence", result["quality"].get("confidence", 0.5))
    result["extraction"].setdefault("method", "llm_with_deterministic_verification")
    result["extraction"].setdefault("unsupportedClaims", [])
    result["extraction"].setdefault("warnings", [])


def _list_at(result: dict, section: str, key: str) -> list:
    value = result.setdefault(section, {}).get(key, [])
    if not isinstance(value, list):
        value = []
    result[section][key] = value
    return value


def _id_prefix(section: str) -> str:
    return {
        "entities": "entity",
        "facts": "fact",
        "events": "event",
        "relationships": "rel",
        "topics": "topic",
        "actions": "action",
        "decisions": "decision",
        "risks": "risk",
        "questions": "question",
    }.get(section, section.rstrip("s"))


def _ensure_record_id(item: dict, prefix: str, index: int, *, aliases: tuple[str, ...] = ()) -> None:
    if isinstance(item.get("id"), str) and item["id"]:
        return
    for alias in aliases:
        value = item.get(alias)
        if isinstance(value, str) and value:
            item["id"] = value if value.startswith(f"{prefix}-") else f"{prefix}-{value}"
            return
    item["id"] = f"{prefix}-{index:03d}"


def _normalize_relationships(result: dict) -> None:
    """Keep malformed LLM graph claims from invalidating an otherwise usable result."""
    known_ids = {
        "participant": _record_ids(result.get("participants", [])),
        "entity": _record_ids(result.get("entities", [])),
        "fact": _record_ids(result.get("facts", [])),
        "event": _record_ids(result.get("events", [])),
        "topic": _record_ids(result.get("topics", [])),
        "action": _record_ids(result.get("actions", [])),
        "decision": _record_ids(result.get("decisions", [])),
        "risk": _record_ids(result.get("risks", [])),
        "question": _record_ids(result.get("questions", [])),
        "meeting": {"meeting"},
    }
    normalized: list[dict] = []
    dropped: list[dict] = []
    for relationship in result.get("relationships", []):
        if not isinstance(relationship, dict):
            dropped.append({"id": "unknown", "reason": "relationship_not_an_object"})
            continue
        from_endpoint = _relationship_endpoint(relationship, "from", "source", known_ids)
        to_endpoint = _relationship_endpoint(relationship, "to", "target", known_ids)
        if from_endpoint is None or to_endpoint is None:
            dropped.append({"id": relationship.get("id", "unknown"), "reason": "missing_or_unknown_endpoint"})
            continue
        relationship["from"] = from_endpoint
        relationship["to"] = to_endpoint
        normalized.append(relationship)
    result["relationships"] = normalized
    if dropped:
        warning = f"Dropped {len(dropped)} malformed relationship claim(s) from LLM output."
        result.setdefault("quality", {}).setdefault("warnings", []).append(warning)
        result.setdefault("extraction", {}).setdefault("warnings", []).append(warning)
        result["extraction"].setdefault("unsupportedClaims", []).extend(
            {"section": "relationships", **item} for item in dropped
        )


def _relationship_endpoint(
    relationship: dict,
    name: str,
    alias: str,
    known_ids: dict[str, set[str]],
) -> dict | None:
    endpoint = relationship.get(name)
    if endpoint is None:
        endpoint = relationship.get(alias)
    if endpoint is None:
        endpoint_id = relationship.get(f"{name}Id") or relationship.get(f"{alias}Id")
        endpoint_type = relationship.get(f"{name}Type") or relationship.get(f"{alias}Type")
        if endpoint_id is not None:
            endpoint = {"id": endpoint_id, "type": endpoint_type}
    if isinstance(endpoint, str):
        endpoint = {"id": endpoint, "type": _infer_endpoint_type(endpoint, known_ids)}
    if not isinstance(endpoint, dict):
        return None
    endpoint_id = endpoint.get("id")
    endpoint_type = endpoint.get("type")
    if not isinstance(endpoint_id, str) or not isinstance(endpoint_type, str):
        return None
    if endpoint_id not in known_ids.get(endpoint_type, set()):
        return None
    return {"type": endpoint_type, "id": endpoint_id}


def _record_ids(values: object) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {
        item["id"]
        for item in values
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def _ensure_executive_summary(result: dict) -> None:
    executive = result.setdefault("summaries", {}).setdefault("executive", {})
    if not isinstance(executive, dict) or str(executive.get("text", "")).strip():
        return
    segments = [
        segment
        for segment in result.get("transcript", {}).get("segments", [])
        if isinstance(segment, dict) and isinstance(segment.get("text"), str) and segment["text"].strip()
    ]
    if not segments:
        return
    evidence = [segment["text"].strip() for segment in segments[:3]]
    citation_ids = [f"cite-{index:03d}" for index in range(1, min(3, len(segments)) + 1)]
    executive["text"] = "Tóm tắt dựa trên transcript: " + " ".join(evidence)
    executive["topicIds"] = executive.get("topicIds") if isinstance(executive.get("topicIds"), list) else []
    executive["citationIds"] = citation_ids
    # This is only a UI/context fallback constructed from the opening
    # transcript snippets. It must never masquerade as a whole-meeting,
    # claim-eligible executive summary.
    executive["lineageStatus"] = "context_only"
    warning = "LLM did not provide an executive summary; a transcript-grounded fallback was used."
    result.setdefault("quality", {}).setdefault("warnings", []).append(warning)
    result.setdefault("extraction", {}).setdefault("warnings", []).append(warning)


def _infer_endpoint_type(endpoint_id: str, known_ids: dict[str, set[str]]) -> str | None:
    for endpoint_type, ids in known_ids.items():
        if endpoint_id in ids:
            return endpoint_type
    return None


def _link_speakers_to_participants(result: dict) -> None:
    participants = [item for item in result.get("participants", []) if isinstance(item, dict)]
    identified = 0
    mentioned_only = 0
    by_speaker_label = {}
    for index, participant in enumerate(participants, start=1):
        participant.setdefault("id", f"participant-{index:03d}")
        participant.setdefault("displayName", participant.get("name") or participant.get("speaker") or participant["id"])
        participant.setdefault("normalizedName", str(participant.get("displayName", "")).strip().lower())
        participant.setdefault("speakerLabels", [])
        participant.setdefault("isAttendee", bool(participant.get("speakerLabels")))
        participant.setdefault("isMentionedOnly", not bool(participant.get("isAttendee")))
        participant.setdefault("confidence", 0.5)
        participant.setdefault("citationIds", [])
        if participant.get("isAttendee"):
            identified += 1
        if participant.get("isMentionedOnly"):
            mentioned_only += 1
        for label in participant.get("speakerLabels", []):
            if isinstance(label, str):
                by_speaker_label[label] = participant["id"]
    speakers = result.get("speakers", {})
    for speaker in speakers.get("items", []):
        if isinstance(speaker, dict):
            label = speaker.get("label")
            if isinstance(label, str) and label in by_speaker_label:
                speaker["mappedParticipantId"] = by_speaker_label[label]
    speakers["identifiedParticipantCount"] = identified
    speakers["mentionedOnlyCount"] = mentioned_only


def _add_deterministic_facts(result: dict) -> None:
    facts = [item for item in result.get("facts", []) if isinstance(item, dict)]
    facts = [
        fact
        for fact in facts
        if (fact.get("subtype") or fact.get("type")) != "participant_count"
    ]
    speakers = result.get("speakers", {})
    speaker_count = int(speakers.get("speakerCount") or 0)
    ignored_segments = int(speakers.get("ignoredSegmentCount") or 0)
    if speaker_count <= 0:
        result["facts"] = facts
        if ignored_segments:
            warning = "Participant count was omitted because no reliable diarization speaker label was available."
            result.setdefault("quality", {}).setdefault("warnings", []).append(warning)
            result.setdefault("extraction", {}).setdefault("warnings", []).append(warning)
        return
    facts.insert(
        0,
        {
            "id": _available_record_id(_WINDOW_PARTICIPANT_COUNT_ID, facts),
            "type": "participant_count",
            "subject": {"type": "meeting", "id": "meeting"},
            "predicate": "has_reliable_speaker_count",
            "value": speaker_count,
            "unit": "people",
            "countBasis": "reliable_diarization_labels",
            "ignoredSegmentCount": ignored_segments,
            "isLowerBound": bool(ignored_segments),
            "confidence": 0.9 if ignored_segments else 0.95 if speaker_count else 0.5,
            "derivedFrom": "speakers",
            "citationIds": [],
        },
    )
    result["facts"] = facts


def _available_record_id(base: str, records: list[dict]) -> str:
    existing = {
        item.get("id")
        for item in records
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if base not in existing:
        return base
    suffix = 2
    while f"{base}-{suffix}" in existing:
        suffix += 1
    return f"{base}-{suffix}"


def _mark_unsupported_claims(result: dict) -> None:
    unsupported = result.setdefault("extraction", {}).setdefault("unsupportedClaims", [])
    warnings = result["extraction"].setdefault("warnings", [])
    for section in ("facts", "events", "relationships", "topics", "actions", "decisions", "risks", "questions"):
        for item in result.get(section, []):
            if not isinstance(item, dict):
                continue
            if item.get("derivedFrom") or item.get("citationIds"):
                continue
            claim_id = item.get("id") or f"{section}:unknown"
            unsupported.append({"section": section, "id": claim_id, "reason": "missing_citation_or_derived_source"})
            if isinstance(item.get("confidence"), int | float):
                item["confidence"] = min(float(item["confidence"]), 0.35)
    if unsupported:
        warnings.append(f"{len(unsupported)} extracted claim(s) have no citation or deterministic source.")
        result["extraction"]["unsupportedClaims"] = unsupported
        result["extraction"]["warnings"] = list(dict.fromkeys(warnings))
