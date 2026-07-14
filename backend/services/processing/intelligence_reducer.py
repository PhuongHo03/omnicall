from collections import OrderedDict
from datetime import UTC, datetime
import hashlib
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

    summary = _reduce_summary(local_results, citations, citation_maps)
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
    for record in _speaker_records(transcript_segments, citations, window_manifest):
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
            "generatedAt": datetime.now(UTC).isoformat(),
        },
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


def _record_from_local(item: dict, section: str, source_window_id: str, citation_map: dict[str, str]) -> dict:
    record_id = item.get("id") or f"{section}-{abs(hash(str(item))) % 100000:05d}"
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


def _reduce_summary(local_results: list[dict], citations: list[dict], citation_maps: list[dict[str, str]]) -> dict:
    texts = []
    citation_ids = []
    for result, citation_map in zip(local_results, citation_maps, strict=True):
        executive = result.get("summaries", {}).get("executive", {})
        if isinstance(executive, dict) and executive.get("text"):
            texts.append(str(executive["text"]).strip())
            citation_ids.extend(citation_map.get(item, item) for item in executive.get("citationIds", []))
    known = {citation["id"] for citation in citations}
    citation_ids = [item for item in dict.fromkeys(citation_ids) if item in known]
    text = " ".join(texts)
    return {
        "executive": {"text": text[:4000], "topicIds": [], "evidenceRefs": citation_ids},
        "topics": [],
        "timeline": [],
    }


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
        label = segment.speaker or "Unknown"
        item = stats.setdefault(label, {"label": label, "segmentCount": 0, "totalTalkTimeMs": 0, "confidence": 0.0})
        item["segmentCount"] += 1
        item["totalTalkTimeMs"] += max(0, (segment.end_ms or 0) - (segment.start_ms or 0))
        item["confidence"] += float(segment.confidence or 0)
    items = []
    for item in stats.values():
        item["confidence"] = round(item["confidence"] / max(1, item["segmentCount"]), 4)
        items.append(item)
    return {"speakerCount": len(items), "identifiedParticipantCount": 0, "mentionedOnlyCount": 0, "items": items}


def _speaker_records(segments: list, citations: list[dict], windows: list[dict]) -> list[dict]:
    """Represent deterministic speaker intelligence as canonical v2 records."""
    grouped: dict[str, dict] = {}
    citation_by_segment = {
        segment_id: citation.get("id")
        for citation in citations
        for segment_id in citation.get("segmentIds", [])
        if isinstance(citation, dict) and isinstance(citation.get("id"), str)
    }
    for segment in segments:
        label = segment.speaker or "Unknown"
        item = grouped.setdefault(label, {"segmentCount": 0, "totalTalkTimeMs": 0, "confidenceTotal": 0.0, "evidenceRefs": []})
        item["segmentCount"] += 1
        item["totalTalkTimeMs"] += max(0, (segment.end_ms or 0) - (segment.start_ms or 0))
        item["confidenceTotal"] += float(segment.confidence or 0)
        if citation_by_segment.get(segment.id):
            item["evidenceRefs"].append(citation_by_segment[segment.id])

    records = []
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
    records.append(build_record(
        record_id="fact-speaker-count",
        record_type="fact",
        subtype="speaker_count",
        data={"value": len(grouped), "unit": "speakers"},
        source_refs=[window["id"] for window in windows if isinstance(window, dict) and isinstance(window.get("id"), str)],
        derived_from=[record["id"] for record in records],
        confidence=1.0,
        status="verified",
    ))
    return records


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
