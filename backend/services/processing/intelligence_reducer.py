from collections import OrderedDict
from datetime import UTC, datetime

from backend.providers.contracts.analysis import SCHEMA_VERSION


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
    speaker_stats = _speaker_stats(transcript_segments)
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
    coverage = {
        "status": "complete",
        "coveredAssetIds": [asset.id],
        "windowCount": len(windows),
        "processedWindowCount": len(local_results),
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
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
        "evidence": {"citations": citations},
        "speakers": speaker_stats,
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
    data = dict(item)
    data.pop("id", None)
    citation_ids = [citation_map.get(item_id, item_id) for item_id in item.get("citationIds", [])]
    data["citationIds"] = list(dict.fromkeys(citation_ids))
    return {
        "id": record_id,
        "type": record_type,
        "scope": "global",
        "data": data,
        "citationIds": list(dict.fromkeys(citation_ids)),
        "sourceWindowIds": [source_window_id],
        "confidence": float(item.get("confidence", 0.5) or 0.5),
        "status": "candidate",
    }


def _merge_record(existing: dict, incoming: dict) -> None:
    existing["citationIds"] = list(dict.fromkeys(existing.get("citationIds", []) + incoming.get("citationIds", [])))
    existing["sourceWindowIds"] = list(dict.fromkeys(existing.get("sourceWindowIds", []) + incoming.get("sourceWindowIds", [])))
    existing["confidence"] = round(max(float(existing.get("confidence", 0)), float(incoming.get("confidence", 0))), 4)
    existing["status"] = "verified" if existing["citationIds"] else "candidate"
    for key, value in incoming.get("data", {}).items():
        if key not in existing["data"] or existing["data"][key] in (None, "", []):
            existing["data"][key] = value


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
        "executive": {"text": text[:4000], "topicIds": [], "citationIds": citation_ids},
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
            "id": f"cite-{index:03d}",
            "segmentIds": [segment.id],
            "startMs": segment.start_ms,
            "endMs": segment.end_ms,
            "speakerLabels": [segment.speaker] if segment.speaker else [],
            "quote": segment.text,
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
