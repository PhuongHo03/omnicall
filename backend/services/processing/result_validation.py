def validate_result_json(result_json: dict) -> None:
    if result_json.get("schemaVersion") == "meeting-intelligence-result.v2" and isinstance(result_json.get("knowledge"), dict):
        _validate_unified_result(result_json)
        return
    raise ValueError("Only meeting-intelligence-result.v2 can be persisted.")

    # Retained below only as historical implementation context; unreachable
    # after the v2 cutover guard above.
    required_top_level = {
        "schemaVersion",
        "meeting",
        "source",
        "transcript",
        "evidence",
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
    }
    missing = required_top_level.difference(result_json)
    if missing:
        raise ValueError(f"Processed result missing sections: {', '.join(sorted(missing))}")

    segments = result_json.get("transcript", {}).get("segments", [])
    if not segments:
        raise ValueError("Processed result must include at least one transcript segment.")

    executive = result_json.get("summaries", {}).get("executive", {})
    if not isinstance(executive, dict) or not executive.get("text"):
        raise ValueError("Processed result must include an executive summary.")

    segment_ids = {segment.get("id") for segment in segments}
    citations = {citation.get("id"): citation for citation in result_json.get("evidence", {}).get("citations", [])}
    for citation in citations.values():
        for segment_id in citation.get("segmentIds", []):
            if segment_id not in segment_ids:
                raise ValueError(f"Citation references unknown transcript segment: {segment_id}")

    participant_ids = _ids(result_json.get("participants", []))
    entity_ids = _ids(result_json.get("entities", []))
    fact_ids = _ids(result_json.get("facts", []))
    event_ids = _ids(result_json.get("events", []))
    topic_ids = _ids(result_json.get("topics", []))
    action_ids = _ids(result_json.get("actions", []))
    decision_ids = _ids(result_json.get("decisions", []))
    risk_ids = _ids(result_json.get("risks", []))
    question_ids = _ids(result_json.get("questions", []))

    for item in _extract_indexed_insights(result_json):
        for citation_id in item.get("citationIds", []):
            if citation_id not in citations:
                raise ValueError(f"Insight references unknown citation: {citation_id}")

    for record in result_json.get("relationships", []):
        if not isinstance(record, dict):
            continue
        for endpoint_name in ("from", "to"):
            endpoint = record.get(endpoint_name)
            if not isinstance(endpoint, dict):
                raise ValueError(f"Relationship missing endpoint: {endpoint_name}")
            if not _known_ref(endpoint, participant_ids, entity_ids, fact_ids, event_ids, topic_ids, action_ids, decision_ids, risk_ids, question_ids):
                raise ValueError(f"Relationship references unknown endpoint: {endpoint}")

    for topic in result_json.get("topics", []):
        if not isinstance(topic, dict):
            continue
        for participant_id in topic.get("participantIds", []):
            if participant_id not in participant_ids:
                raise ValueError(f"Topic references unknown participant: {participant_id}")
        for fact_id in topic.get("factIds", []):
            if fact_id not in fact_ids:
                raise ValueError(f"Topic references unknown fact: {fact_id}")
        for event_id in topic.get("eventIds", []):
                if event_id not in event_ids:
                    raise ValueError(f"Topic references unknown event: {event_id}")


def _validate_unified_result(result_json: dict) -> None:
    required_top_level = {"schemaVersion", "document", "transcript", "evidence", "knowledge", "summaries", "quality", "extraction"}
    missing = required_top_level.difference(result_json)
    if missing:
        raise ValueError(f"Unified result missing sections: {', '.join(sorted(missing))}")
    segments = result_json.get("transcript", {}).get("segments", [])
    if not isinstance(segments, list) or not segments:
        raise ValueError("Unified result must include transcript segments.")
    segment_ids = {segment.get("id") for segment in segments if isinstance(segment, dict)}
    evidence = result_json.get("evidence", {})
    citations = evidence.get("items", []) if isinstance(evidence, dict) else []
    citation_ids = {citation.get("id") for citation in citations if isinstance(citation, dict)}
    if len(citation_ids) != len(citations):
        raise ValueError("Evidence item IDs must be unique and non-empty.")
    for citation in citations:
        if not isinstance(citation, dict):
            raise ValueError("Evidence citations must be objects.")
        unknown = set(citation.get("segmentIds", [])) - segment_ids
        if unknown:
            raise ValueError(f"Citation references unknown transcript segments: {', '.join(sorted(unknown))}")
        if citation.get("kind") in {"structured", "derived"} and citation.get("segmentIds"):
            raise ValueError(f"Structured or derived evidence cannot reference transcript segments: {citation.get('id')}")
    knowledge = result_json["knowledge"]
    records = knowledge.get("records", [])
    if not isinstance(records, list):
        raise ValueError("knowledge.records must be a list.")
    record_ids = {record.get("id") for record in records if isinstance(record, dict)}
    if len(record_ids) != len(records):
        raise ValueError("Knowledge record IDs must be unique.")
    window_ids = {window.get("id") for window in result_json.get("transcript", {}).get("windows", []) if isinstance(window, dict)}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not isinstance(record.get("type"), str):
            raise ValueError("Every knowledge record requires an id and type.")
        from backend.services.knowledge.contract import validate_record_shape

        validate_record_shape(record)
        if set(record.get("evidenceRefs", [])) - citation_ids:
            raise ValueError(f"Knowledge record references unknown evidence: {record.get('id')}")
        if window_ids and set(record.get("sourceRefs", [])) - window_ids:
            raise ValueError(f"Knowledge record references an unknown source reference: {record.get('id')}")
    for relationship in knowledge.get("relationships", []):
        if not isinstance(relationship, dict):
            raise ValueError("Knowledge relationships must be objects.")
        for endpoint in (relationship.get("from"), relationship.get("to")):
            if not isinstance(endpoint, dict) or endpoint.get("id") not in record_ids:
                raise ValueError("Knowledge relationship references an unknown record.")
    executive = result_json.get("summaries", {}).get("executive", {})
    if not isinstance(executive, dict) or not executive.get("text"):
        raise ValueError("Unified result must include an executive summary.")


def append_voice_quality_warnings(result_json: dict, voice_metadata: dict) -> None:
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
    extraction = result_json.setdefault("extraction", {})
    extraction_warnings = extraction.setdefault("warnings", [])
    if isinstance(extraction_warnings, list):
        extraction["warnings"] = list(dict.fromkeys([*extraction_warnings, *warnings]))


def _extract_indexed_insights(result_json: dict) -> list[dict]:
    insights: list[dict] = []
    citations_by_id = {citation.get("id"): citation for citation in result_json.get("evidence", {}).get("items", [])}
    summaries = result_json.get("summaries", {})
    executive = summaries.get("executive", {}) if isinstance(summaries, dict) else {}
    if isinstance(executive, dict) and executive.get("text"):
        insights.append(
            {
                "section": "summary.executive",
                "itemId": "summary-executive",
                "title": "Executive summary",
                "text": executive["text"],
                "citationIds": list(executive.get("citationIds", [])),
                "segmentIds": [],
                "payload": executive,
            }
        )
    for section in ("participants", "entities", "facts", "events", "relationships", "topics", "actions", "decisions", "risks", "questions"):
        values = result_json.get(section, [])
        if not isinstance(values, list):
            continue
        for index, item in enumerate(values, start=1):
            if isinstance(item, dict):
                insights.append(_indexed_item(section, index, item, citations_by_id))
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


def _ids(values: object) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {item.get("id") for item in values if isinstance(item, dict) and isinstance(item.get("id"), str)}


def _known_ref(
    endpoint: dict,
    participant_ids: set[str],
    entity_ids: set[str],
    fact_ids: set[str],
    event_ids: set[str],
    topic_ids: set[str],
    action_ids: set[str],
    decision_ids: set[str],
    risk_ids: set[str],
    question_ids: set[str],
) -> bool:
    endpoint_type = endpoint.get("type")
    endpoint_id = endpoint.get("id")
    lookup = {
        "participant": participant_ids,
        "entity": entity_ids,
        "fact": fact_ids,
        "event": event_ids,
        "topic": topic_ids,
        "action": action_ids,
        "action_item": action_ids,
        "decision": decision_ids,
        "risk": risk_ids,
        "question": question_ids,
        "meeting": {"meeting"},
    }
    return isinstance(endpoint_id, str) and endpoint_id in lookup.get(endpoint_type, set())
