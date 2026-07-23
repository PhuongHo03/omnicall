from collections import OrderedDict
from datetime import UTC, datetime
import hashlib
import json
import re
import unicodedata

from backend.services.knowledge.contract import KNOWLEDGE_SCHEMA_VERSION
from backend.services.knowledge.contract import build_record
from backend.services.knowledge.evidence import build_evidence_item
from backend.services.knowledge.normalization import normalize_candidate


RECORD_SECTIONS = (
    "participants",
    "entities",
    "facts",
    "events",
    "topics",
    "actions",
    "decisions",
    "risks",
    "questions",
)

_GLOBAL_PARTICIPANT_COUNT_ID = "derived-transcript-participant-count"
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


def reduce_window_results(
    *,
    meeting,
    asset,
    transcript_segments: list,
    windows: list[dict],
    local_results: list[dict],
    provider_name: str,
    provider_model: str,
) -> dict:
    provider_executions = _provider_executions(local_results)
    if provider_executions:
        provider_name = provider_executions[0]["provider"] if len(provider_executions) == 1 else "multiple"
        provider_model = provider_executions[0]["model"] if len(provider_executions) == 1 else "multiple"
    citations = _build_citations(transcript_segments)
    records: OrderedDict[str, dict] = OrderedDict()
    relationships: OrderedDict[str, dict] = OrderedDict()
    warnings: list[str] = []
    citation_maps: list[dict[str, str]] = []

    for window, local in zip(windows, local_results, strict=True):
        source_window_id = window["windowId"]
        citation_map = _citation_map(local, citations)
        citation_maps.append(citation_map)
        for section in RECORD_SECTIONS:
            for item in local.get(section, []) if isinstance(local.get(section), list) else []:
                if not isinstance(item, dict):
                    continue
                if section == "facts" and _is_window_participant_count(item):
                    continue
                record = _record_from_local(item, section, source_window_id, citation_map)
                record_id = record["id"]
                existing = records.get(record_id)
                if existing is None:
                    records[record_id] = record
                else:
                    _merge_record(existing, record)
        for item in local.get("relationships", []) if isinstance(local.get("relationships"), list) else []:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            record = _record_from_local(item, "relationship", source_window_id, citation_map)
            record["from"] = record["data"].get("from")
            record["to"] = record["data"].get("to")
            existing = relationships.get(record["id"])
            if existing is None:
                relationships[record["id"]] = record
            else:
                _merge_record(existing, record)
        for warning in _warnings(local):
            warnings.append(f"{source_window_id}: {warning}")

    _drop_unsupported_semantic_records(records, citations)
    summary = _reduce_summary(local_results, citations, citation_maps, windows)
    if (
        summary.get("executive", {}).get("text")
        and not summary.get("executive", {}).get("evidenceRefs")
    ):
        warnings.append(
            "Executive summary was retained as context only because its source windows did not provide citation lineage."
        )
    window_manifest = [
        {
            "id": window["windowId"],
            "sequenceNo": window["sequenceNo"],
            "startMs": window.get("startMs"),
            "endMs": window.get("endMs"),
            "segmentIds": window.get("segmentIds", []),
        }
        for window in windows
    ]
    speaker_stats = _speaker_stats(transcript_segments)
    if not speaker_stats.get("speakerCount") and speaker_stats.get("ignoredSegmentCount"):
        warnings.append("Participant count was omitted because no reliable diarization speaker label was available.")
    for record in _speaker_records(
        transcript_segments,
        citations,
        window_manifest,
        speaker_stats,
        existing_record_ids=set(records),
    ):
        existing = records.get(record["id"])
        if existing is None:
            records[record["id"]] = record
        else:
            _merge_record(existing, record)
    for relationship in _infer_identity_relationships(records, transcript_segments, citations, window_manifest):
        relationships.setdefault(relationship["id"], relationship)
    _attach_derived_citations(records, citations)
    coverage = {
        "status": "complete",
        "coveredAssetIds": [asset.id],
        "windowCount": len(windows),
        "processedWindowCount": len(local_results),
    }
    return {
        "schemaVersion": KNOWLEDGE_SCHEMA_VERSION,
        "document": {
            "meetingId": meeting.id,
            "assetIds": [asset.id],
            "title": meeting.title,
            "generatedAt": datetime.now(UTC).isoformat(),
        },
        "meeting": {"id": meeting.id, "title": meeting.title},
        "source": {
            "assetIds": [asset.id],
            "analysisProvider": "hierarchical-llm-analysis",
            "analysisModel": provider_model,
            "llmProvider": provider_name,
            "providerExecutions": provider_executions,
            "fallbackUsed": any(bool(item.get("fallbackUsed")) for item in provider_executions),
            "generatedAt": datetime.now(UTC).isoformat(),
        },
        "speakers": speaker_stats,
        "transcript": {
            "segments": [_segment_json(segment) for segment in transcript_segments],
            "windows": window_manifest,
            "coverage": coverage,
        },
        "evidence": {"items": citations},
        "knowledge": {
            "records": list(records.values()),
            "relationships": list(relationships.values()),
        },
        "summaries": summary,
        "quality": {
            "coverage": "complete",
            "warnings": list(dict.fromkeys(warnings)),
            "confidence": _average_confidence(list(records.values())),
        },
        "extraction": {
            "overallConfidence": _average_confidence(list(records.values())),
            "method": "hierarchical_map_reduce",
            "windowCount": len(windows),
            "processedWindowCount": len(local_results),
            "coverage": 1.0 if windows and len(windows) == len(local_results) else 0.0,
            "unsupportedClaims": [],
            "warnings": list(dict.fromkeys(warnings)),
        },
    }


def _provider_executions(local_results: list[dict]) -> list[dict]:
    counts: OrderedDict[tuple[str, str | None, bool, str | None, str | None], int] = OrderedDict()
    for local in local_results:
        source = local.get("source", {}) if isinstance(local, dict) else {}
        provider = source.get("llmProvider")
        model = source.get("analysisModel")
        if not isinstance(provider, str) or not provider:
            continue
        key = (
            provider,
            model if isinstance(model, str) and model else None,
            bool(source.get("fallbackUsed", False)),
            source.get("primaryErrorType") if isinstance(source.get("primaryErrorType"), str) else None,
            source.get("primaryErrorMessage") if isinstance(source.get("primaryErrorMessage"), str) else None,
        )
        counts[key] = counts.get(key, 0) + 1
    return [
        {
            "provider": provider,
            "model": model,
            "fallbackUsed": fallback,
            "primaryErrorType": error_type,
            "primaryErrorMessage": error_message,
            "windowCount": count,
        }
        for (provider, model, fallback, error_type, error_message), count in counts.items()
    ]


def _record_from_local(item: dict, section: str, source_window_id: str, citation_map: dict[str, str]) -> dict:
    record_id = item.get("id") or _stable_candidate_id(section, item)
    record_type = {
        "participants": "participant",
        "entities": "entity",
        "facts": "fact",
        "events": "event",
        "topics": "topic",
        "actions": "action",
        "decisions": "decision",
        "risks": "risk",
        "questions": "question",
        "relationship": "relationship",
    }.get(section, section)
    citation_ids = [citation_map.get(item_id, item_id) for item_id in item.get("citationIds", [])]
    return normalize_candidate(
        item=item,
        section=section,
        record_id=record_id,
        source_ref=source_window_id,
        evidence_refs=list(dict.fromkeys(citation_ids)),
    )


def _stable_candidate_id(section: str, item: dict) -> str:
    payload = {
        key: value
        for key, value in item.items()
        if key not in {"citationIds", "confidence", "sourceWindowIds"}
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:12]
    prefix = {
        "participants": "participant",
        "entities": "entity",
        "facts": "fact",
        "events": "event",
        "topics": "topic",
        "actions": "action",
        "decisions": "decision",
        "risks": "risk",
        "questions": "question",
        "relationship": "relationship",
    }.get(section, section.rstrip("s"))
    return f"{prefix}-{digest}"


def _is_window_participant_count(item: dict) -> bool:
    return (
        (item.get("subtype") or item.get("type")) == "participant_count"
        and item.get("derivedFrom") == "speakers"
        and str(item.get("predicate") or "").startswith("has_")
    )


def _merge_record(existing: dict, incoming: dict) -> None:
    existing["evidenceRefs"] = list(dict.fromkeys(existing.get("evidenceRefs", []) + incoming.get("evidenceRefs", [])))
    existing["sourceRefs"] = list(dict.fromkeys(existing.get("sourceRefs", []) + incoming.get("sourceRefs", [])))
    existing["derivedFrom"] = list(dict.fromkeys(existing.get("derivedFrom", []) + incoming.get("derivedFrom", [])))
    existing["confidence"] = round(max(float(existing.get("confidence", 0)), float(incoming.get("confidence", 0))), 4)
    existing["status"] = "verified" if existing["evidenceRefs"] or existing["derivedFrom"] else "candidate"
    for key, value in incoming.get("data", {}).items():
        if key not in existing["data"] or existing["data"][key] in (None, "", []):
            existing["data"][key] = value


def _attach_derived_citations(records: OrderedDict[str, dict], citations: list[dict]) -> None:
    """Cite deterministic facts that are derived from the complete transcript."""
    citation_ids = [citation.get("id") for citation in citations if isinstance(citation.get("id"), str)]
    for record in records.values():
        data = record.get("data", {})
        if (
            record.get("type") == "fact"
            and data.get("type") == "participant_count"
            and "transcript.segments" in record.get("derivedFrom", [])
            and not record.get("evidenceRefs")
        ):
            record["status"] = "verified" if data.get("derivedFrom") else "candidate"


def _reduce_summary(
    local_results: list[dict],
    citations: list[dict],
    citation_maps: list[dict[str, str]],
    windows: list[dict],
) -> dict:
    texts = []
    citation_ids = []
    covered_window_ids: list[str] = []
    sentences: list[dict] = []
    for result, citation_map, window in zip(local_results, citation_maps, windows, strict=True):
        executive = result.get("summaries", {}).get("executive", {})
        if isinstance(executive, dict) and executive.get("text"):
            summary_text = str(executive["text"]).strip()
            texts.append(summary_text)
            context_only = executive.get("lineageStatus") == "context_only"
            if not context_only:
                covered_window_ids.append(window["windowId"])
            local_citation_ids = executive.get("citationIds", [])
            if not isinstance(local_citation_ids, list):
                local_citation_ids = []
            mapped_refs = [] if context_only else [
                citation_map.get(item, item)
                for item in local_citation_ids
                if isinstance(item, str)
            ]
            citation_ids.extend(mapped_refs)
            sentences.append({"text": summary_text, "evidenceRefs": mapped_refs, "coveredWindowIds": [] if context_only else [window["windowId"]]})
            # A provider may link an executive summary to typed topics while
            # omitting the duplicate citationIds field.  Preserve that
            # explicit graph lineage, but never infer that every citation in
            # the window supports the whole summary.
            if not context_only and not local_citation_ids:
                referenced_topic_ids = {
                    item
                    for item in executive.get("topicIds", [])
                    if isinstance(item, str)
                }
                for topic in result.get("topics", []) if isinstance(result.get("topics"), list) else []:
                    if not isinstance(topic, dict) or topic.get("id") not in referenced_topic_ids:
                        continue
                    citation_ids.extend(
                        citation_map.get(item, item)
                        for item in topic.get("citationIds", [])
                        if isinstance(item, str)
                    )
    known = {citation["id"] for citation in citations}
    citation_ids = [item for item in dict.fromkeys(citation_ids) if item in known]
    text = " ".join(texts)
    coverage_ratio = len(set(covered_window_ids)) / len(windows) if windows else 0.0
    whole_meeting = bool(windows) and coverage_ratio == 1.0 and bool(citation_ids)
    return {
        "executive": {
            "text": text[:4000],
            "topicIds": [],
            "evidenceRefs": citation_ids if whole_meeting else [],
            "coveredWindowIds": list(dict.fromkeys(covered_window_ids)),
            "coverageRatio": round(coverage_ratio, 4),
            "sentences": sentences,
            "lineageStatus": "verified" if whole_meeting else "context_only",
        },
        "topics": [],
        "timeline": [],
    }


def _drop_unsupported_semantic_records(records: OrderedDict[str, dict], citations: list[dict]) -> None:
    """Drop semantic records whose cited transcript cannot establish provenance."""
    known = {item.get("id") for item in citations if isinstance(item, dict)}
    for record_id, record in list(records.items()):
        if record.get("type") not in {"action", "decision", "risk", "question", "topic"}:
            continue
        refs = [ref for ref in record.get("evidenceRefs", []) if ref in known]
        if not refs:
            del records[record_id]
    action_signatures = {
        _semantic_record_signature(record)
        for record in records.values()
        if record.get("type") == "action"
    }
    for record_id, record in list(records.items()):
        if record.get("type") == "decision" and _semantic_record_signature(record) in action_signatures:
            del records[record_id]


def _semantic_record_signature(record: dict) -> str:
    data = record.get("data", {})
    text = " ".join(
        str(data.get(key) or "")
        for key in ("text", "summary", "task", "decision", "title", "name")
    )
    return " ".join(_normalized_name(text).split())


def _citation_map(local: dict, global_citations: list[dict]) -> dict[str, str]:
    global_by_segment = {
        segment_id: citation["id"]
        for citation in global_citations
        for segment_id in citation.get("segmentIds", [])
    }
    mapping: dict[str, str] = {}
    for citation in local.get("evidence", {}).get("citations", []) if isinstance(local.get("evidence", {}).get("citations", []), list) else []:
        if not isinstance(citation, dict) or not citation.get("id"):
            continue
        for segment_id in citation.get("segmentIds", []):
            if segment_id in global_by_segment:
                mapping[citation["id"]] = global_by_segment[segment_id]
                break
    return mapping


def _build_citations(segments: list) -> list[dict]:
    return [
        {
            **build_evidence_item(
                evidence_id=f"cite-{index:03d}",
                kind="transcript",
                segment_ids=[segment.id],
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                quote=segment.text,
            ),
            "speakerLabels": [segment.speaker] if segment.speaker else [],
            "evidenceType": "direct_quote",
        }
        for index, segment in enumerate(segments, start=1)
    ]


def _segment_json(segment) -> dict:
    return {
        "id": segment.id,
        "speakerLabel": segment.speaker,
        "speaker": segment.speaker,
        "startMs": segment.start_ms,
        "endMs": segment.end_ms,
        "text": segment.text,
        "confidence": segment.confidence,
    }


def _speaker_stats(segments: list) -> dict:
    stats: dict[str, dict] = {}
    for segment in segments:
        label = _speaker_label(segment.speaker)
        item = stats.setdefault(
            label,
            {
                "label": label,
                "segmentCount": 0,
                "totalTalkTimeMs": 0,
                "confidence": 0.0,
                "countsTowardParticipantCount": _is_countable_speaker_label(label),
            },
        )
        item["segmentCount"] += 1
        item["totalTalkTimeMs"] += max(0, (segment.end_ms or 0) - (segment.start_ms or 0))
        item["confidence"] += float(segment.confidence or 0)
    items = []
    for item in stats.values():
        item["confidence"] = round(item["confidence"] / max(1, item["segmentCount"]), 4)
        items.append(item)
    items.sort(key=lambda item: str(item["label"]))
    counted_items = [item for item in items if item["countsTowardParticipantCount"]]
    ignored_items = [item for item in items if not item["countsTowardParticipantCount"]]
    reconciled_ignored_segments = sum(
        1
        for index, segment in enumerate(segments)
        if not _is_countable_speaker_label(_speaker_label(segment.speaker))
        and _ignored_segment_is_reconciled(segments, index)
    )
    ignored_segment_count = sum(
        int(item["segmentCount"])
        for item in ignored_items
    )
    unresolved_ignored_segments = max(
        0,
        ignored_segment_count - reconciled_ignored_segments,
    )
    return {
        "speakerCount": len(counted_items),
        "speakerCountExact": bool(counted_items) and unresolved_ignored_segments == 0,
        "identifiedParticipantCount": 0,
        "mentionedOnlyCount": 0,
        "ignoredSpeakerLabelCount": len(ignored_items),
        "ignoredSegmentCount": ignored_segment_count,
        "reconciledIgnoredSegmentCount": reconciled_ignored_segments,
        "unresolvedIgnoredSegmentCount": unresolved_ignored_segments,
        "items": items,
    }


def _speaker_records(
    segments: list,
    citations: list[dict],
    windows: list[dict],
    speaker_stats: dict | None = None,
    existing_record_ids: set[str] | None = None,
) -> list[dict]:
    """Represent deterministic speaker intelligence as canonical v2 records."""
    speaker_stats = speaker_stats or _speaker_stats(segments)
    countable_labels = {
        item["label"]
        for item in speaker_stats.get("items", [])
        if isinstance(item, dict)
        and item.get("countsTowardParticipantCount")
        and isinstance(item.get("label"), str)
    }
    grouped: dict[str, dict] = {}
    citation_by_segment = {
        segment_id: citation.get("id")
        for citation in citations
        for segment_id in citation.get("segmentIds", [])
        if isinstance(citation, dict) and isinstance(citation.get("id"), str)
    }
    for segment in segments:
        label = _speaker_label(segment.speaker)
        if label not in countable_labels:
            continue
        item = grouped.setdefault(label, {"segmentCount": 0, "totalTalkTimeMs": 0, "confidenceTotal": 0.0, "evidenceRefs": []})
        item["segmentCount"] += 1
        item["totalTalkTimeMs"] += max(0, (segment.end_ms or 0) - (segment.start_ms or 0))
        item["confidenceTotal"] += float(segment.confidence or 0)
        if citation_by_segment.get(segment.id):
            item["evidenceRefs"].append(citation_by_segment[segment.id])

    records = []
    reserved_ids = set(existing_record_ids or ())
    for label, values in grouped.items():
        speaker_id = f"speaker-{hashlib.sha1(label.strip().lower().encode('utf-8')).hexdigest()[:12]}"
        records.append(build_record(
            record_id=speaker_id,
            record_type="participant",
            subtype="speaker_profile",
            data={
                "displayName": label,
                "segmentCount": values["segmentCount"],
                "totalTalkTimeMs": values["totalTalkTimeMs"],
                "averageConfidence": round(values["confidenceTotal"] / max(1, values["segmentCount"]), 4),
            },
            evidence_refs=list(dict.fromkeys(values["evidenceRefs"])),
            source_refs=[window["id"] for window in windows if isinstance(window, dict) and isinstance(window.get("id"), str)],
            derived_from=["transcript.segments"],
            confidence=round(values["confidenceTotal"] / max(1, values["segmentCount"]), 4),
            status="verified",
        ))
        reserved_ids.add(speaker_id)
    if speaker_stats.get("speakerCount"):
        speaker_count_exact = speaker_stats.get("speakerCountExact") is True
        records.append(build_record(
            record_id=_available_record_id(_GLOBAL_PARTICIPANT_COUNT_ID, reserved_ids),
            record_type="fact",
            subtype="participant_count",
            data={
                "subject": {"type": "meeting", "id": "meeting"},
                "predicate": "has_reliable_speaker_count",
                "value": int(speaker_stats.get("speakerCount") or 0),
                "unit": "people",
                "countBasis": "reliable_diarization_labels",
                "ignoredSpeakerLabelCount": int(speaker_stats.get("ignoredSpeakerLabelCount") or 0),
                "ignoredSegmentCount": int(speaker_stats.get("ignoredSegmentCount") or 0),
                "reconciledIgnoredSegmentCount": int(
                    speaker_stats.get("reconciledIgnoredSegmentCount") or 0
                ),
                "unresolvedIgnoredSegmentCount": int(
                    speaker_stats.get("unresolvedIgnoredSegmentCount") or 0
                ),
                "countCompleteness": "exact" if speaker_count_exact else "lower_bound",
                "isLowerBound": not speaker_count_exact,
            },
            source_refs=[window["id"] for window in windows if isinstance(window, dict) and isinstance(window.get("id"), str)],
            derived_from=[record["id"] for record in records],
            confidence=1.0 if speaker_count_exact else 0.9,
            status="verified",
        ))
    return records


def _available_record_id(base: str, existing_ids: set[str]) -> str:
    if base not in existing_ids:
        return base
    suffix = 2
    while f"{base}-{suffix}" in existing_ids:
        suffix += 1
    return f"{base}-{suffix}"


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


def _ignored_segment_is_reconciled(segments: list, index: int) -> bool:
    """Prove an ignored diarization segment cannot introduce another speaker."""
    segment = segments[index]
    label = _normalized_speaker_label(getattr(segment, "speaker", None))
    if label in {
        "background",
        "background noise",
        "crosstalk",
        "noise",
        "overlap",
        "silence",
    }:
        return True
    duration_ms = max(
        0,
        int(getattr(segment, "end_ms", 0) or 0)
        - int(getattr(segment, "start_ms", 0) or 0),
    )
    if duration_ms > 10_000:
        return False

    previous = segments[index - 1] if index > 0 else None
    following = segments[index + 1] if index + 1 < len(segments) else None
    previous_label = _adjacent_countable_speaker(previous, segment, before=True)
    following_label = _adjacent_countable_speaker(following, segment, before=False)
    if previous_label and following_label:
        return previous_label == following_label
    if previous_label and following is None:
        return True
    if following_label and previous is None:
        return True
    return False


def _adjacent_countable_speaker(neighbor, segment, *, before: bool) -> str | None:
    if neighbor is None:
        return None
    label = _speaker_label(getattr(neighbor, "speaker", None))
    if not _is_countable_speaker_label(label):
        return None
    gap_ms = (
        int(getattr(segment, "start_ms", 0) or 0)
        - int(getattr(neighbor, "end_ms", 0) or 0)
        if before
        else int(getattr(neighbor, "start_ms", 0) or 0)
        - int(getattr(segment, "end_ms", 0) or 0)
    )
    return label if -250 <= gap_ms <= 500 else None


def _normalized_speaker_label(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "")).encode(
        "ascii",
        "ignore",
    ).decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", normalized.casefold()).strip()


def _infer_identity_relationships(
    records: OrderedDict[str, dict],
    segments: list,
    citations: list[dict],
    windows: list[dict],
) -> list[dict]:
    """Persist only identity links supported by explicit transcript evidence.

    The extractor may identify a person in a participant record while diarization
    only knows a label such as ``Speaker 2``.  A self-introduction is a safe,
    provider-independent bridge between those records.  We intentionally do not
    infer an identity merely because a speaker is addressed by name: that is a
    mention, not proof that the addressed person owns the audio channel.
    """
    speaker_profiles = {
        _normalized_name(record.get("data", {}).get("displayName")): record
        for record in records.values()
        if record.get("type") == "participant" and record.get("subtype") == "speaker_profile"
    }
    named_participants = {
        _normalized_name(record.get("data", {}).get("displayName")): record
        for record in records.values()
        if record.get("type") == "participant"
        and record.get("subtype") != "speaker_profile"
        and record.get("data", {}).get("displayName")
    }
    if not speaker_profiles or not named_participants:
        return []
    citation_by_segment = {
        segment_id: citation.get("id")
        for citation in citations
        for segment_id in citation.get("segmentIds", [])
        if isinstance(citation, dict) and isinstance(citation.get("id"), str)
    }
    relationships = []
    for segment in segments:
        label = _normalized_name(getattr(segment, "speaker", None) or "")
        speaker = speaker_profiles.get(label)
        if speaker is None:
            continue
        text = str(getattr(segment, "text", None) or "")
        normalized_text = _normalized_name(text)
        if not _is_self_introduction(normalized_text):
            continue
        for name, participant in named_participants.items():
            if not name or not _name_in_text(name, normalized_text):
                continue
            evidence_ref = citation_by_segment.get(getattr(segment, "id", None))
            relation_id = "identity-" + hashlib.sha1(
                f"{speaker['id']}:{participant['id']}".encode("utf-8")
            ).hexdigest()[:12]
            relation = build_record(
                record_id=relation_id,
                record_type="relationship",
                subtype="identity_resolution",
                data={
                    "from": {"id": speaker["id"], "type": "participant"},
                    "to": {"id": participant["id"], "type": "participant"},
                    "relationType": "identified_as",
                    "confidence": 0.95,
                },
                evidence_refs=[evidence_ref] if evidence_ref else [],
                source_refs=[
                    window["id"] for window in windows
                    if isinstance(window, dict) and isinstance(window.get("id"), str)
                ],
                derived_from=[getattr(segment, "id", "")],
                confidence=0.95,
                status="verified",
            )
            relation["from"] = relation["data"]["from"]
            relation["to"] = relation["data"]["to"]
            relationships.append(relation)
    return list({item["id"]: item for item in relationships}.values())


def _normalized_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _is_self_introduction(text: str) -> bool:
    return bool(re.search(r"\b(?:this is|i am|i m|my name is|im|toi la|minh la|em la|ten toi la|ten minh la|ten em la)\b", text))


def _name_in_text(name: str, text: str) -> bool:
    return bool(re.search(rf"\b{re.escape(name)}\b", text))


def _average_confidence(records: list[dict]) -> float:
    if not records:
        return 0.5
    return round(sum(float(record.get("confidence", 0.5)) for record in records) / len(records), 4)


def _warnings(result: dict) -> list[str]:
    values = []
    for section in ("quality", "extraction"):
        warnings = result.get(section, {}).get("warnings", [])
        if isinstance(warnings, list):
            values.extend(str(item) for item in warnings if item)
    return values
