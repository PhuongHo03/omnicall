import re

from backend.providers.embedding_provider import TextEmbeddingProvider
from backend.services.retrieval.section_registry import SECTION_TYPE_SET
from backend.services.retrieval.chunk_text import (
    citation_ids as _citation_ids,
    citations_by_id as _citations_by_id,
    elapsed_ms,
    is_signal_text as _is_signal_text,
    is_transcript_signal_text as _is_transcript_signal_text,
    labelize as _labelize,
    metadata_text as _metadata_text,
    record_id as _record_id,
    record_label as _record_label,
    section_items as _section_items,
    tokens as _tokens,
)


SECTION_PRIORITY = {
    "meeting.metadata": 5,
    "source.processing": 10,
    "speaker.stats": 15,
    "fact.participant_count": 20,
    "fact.record": 30,
    "participant.overview": 35,
    "participant.profile": 40,
    "action.item": 50,
    "decision.record": 55,
    "event.timeline": 60,
    "relationship.edge": 70,
    "risk.record": 80,
    "question.record": 90,
    "observation.record": 110,
    "entity.profile": 100,
    "topic.summary": 130,
    "summary.executive": 150,
    "summary.topic": 155,
    "summary.timeline": 160,
    "quality.overview": 190,
    "quality.warning": 191,
    "extraction.overview": 200,
    "extraction.warning": 201,
    "transcript.coverage": 210,
    "evidence.map": 450,
    "transcript.window": 500,
}


def build_retrieval_chunks(result_json: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    if result_json.get("schemaVersion") != "meeting-intelligence-result.v2":
        raise ValueError("Retrieval indexing requires meeting-intelligence-result.v2.")
    if not isinstance(result_json.get("knowledge"), dict) or not isinstance(result_json.get("evidence", {}).get("items"), list):
        raise ValueError("Retrieval indexing requires JSON v2 knowledge.records and evidence.items.")
    result_json = _canonical_record_view(result_json)
    citations_by_id = _citations_by_id(result_json)
    chunks: list[dict] = []
    chunks.extend(_metadata_chunks(result_json, citations_by_id, embedding_provider))
    chunks.extend(_speaker_chunks(result_json, citations_by_id, embedding_provider))
    chunks.extend(_participant_chunks(result_json, citations_by_id, embedding_provider))
    chunks.extend(_record_chunks(result_json, citations_by_id, embedding_provider))
    chunks.extend(_topic_chunks(result_json, citations_by_id, embedding_provider))
    chunks.extend(_summary_chunks(result_json, citations_by_id, embedding_provider))
    chunks.extend(_transcript_window_chunks(result_json, citations_by_id, embedding_provider))
    _attach_embeddings(chunks, embedding_provider)
    unknown_sections = {chunk.get("sectionType") for chunk in chunks} - SECTION_TYPE_SET
    if unknown_sections:
        raise ValueError(f"Retrieval builder emitted unregistered sections: {sorted(unknown_sections)}")
    return chunks


def _canonical_record_view(result_json: dict) -> dict:
    """Build the indexed view from v2 records; this is not a v1 compatibility adapter."""
    knowledge = result_json.get("knowledge")
    if not isinstance(knowledge, dict):
        raise ValueError("JSON v2 knowledge section is required for retrieval indexing.")
    view = dict(result_json)
    sections = {section: [] for section in ("participants", "entities", "facts", "events", "topics", "relationships", "actions", "decisions", "risks", "questions", "observations")}
    record_sections = {
        "participant": "participants",
        "entity": "entities",
        "fact": "facts",
        "event": "events",
        "topic": "topics",
        "relationship": "relationships",
        "action": "actions",
        "decision": "decisions",
        "risk": "risks",
        "question": "questions",
        "observation": "observations",
    }
    for record in knowledge.get("records", []):
        if not isinstance(record, dict):
            continue
        section = record_sections.get(record.get("type", ""))
        if section not in sections:
            continue
        item = dict(record.get("data", {}))
        item["id"] = record.get("id")
        item["subtype"] = record.get("subtype")
        item["recordType"] = record.get("type")
        item["citationIds"] = record.get("evidenceRefs", [])
        item["evidenceRefs"] = record.get("evidenceRefs", [])
        item["sourceWindowIds"] = record.get("sourceRefs", [])
        item["sourceRefs"] = record.get("sourceRefs", [])
        item["derivedFrom"] = record.get("derivedFrom", [])
        item["confidence"] = record.get("confidence", item.get("confidence", 0.5))
        sections[section].append(item)
    view.update(sections)
    sections["relationships"].extend(
        item for item in knowledge.get("relationships", []) if isinstance(item, dict)
    )
    view["relationships"] = sections["relationships"]
    summaries = dict(view.get("summaries", {}))
    if "topics" in summaries and "topicLevel" not in summaries:
        summaries["topicLevel"] = summaries.pop("topics")
    if "timeline" in summaries and "timelineLevel" not in summaries:
        summaries["timelineLevel"] = summaries.pop("timeline")
    view["summaries"] = summaries
    return view


def _attach_embeddings(chunks: list[dict], embedding_provider: TextEmbeddingProvider) -> None:
    if not chunks:
        return
    embed_texts = getattr(embedding_provider, "embed_texts", None)
    embeddings = (
        list(embed_texts([chunk["text"] for chunk in chunks]))
        if callable(embed_texts)
        else [embedding_provider.embed_text(chunk["text"]) for chunk in chunks]
    )
    if len(embeddings) != len(chunks):
        raise ValueError(f"Embedding provider returned {len(embeddings)} vectors for {len(chunks)} chunks.")
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        if not isinstance(embedding.vector, list) or not embedding.vector:
            raise ValueError(f"Embedding provider returned an empty vector for {chunk['chunkId']}.")
        chunk["embedding"] = embedding.vector
        chunk["metadata"].update(
            {
                "embeddingProvider": embedding.provider_name,
                "embeddingModel": embedding.model_name,
                "embeddingDimensions": len(embedding.vector),
                "embeddingContractVersion": embedding.contract_version,
                "embeddingIdentity": (
                    f"{embedding.provider_name}:{embedding.model_name}:"
                    f"{embedding.contract_version}:{len(embedding.vector)}"
                ),
            }
        )


def _metadata_chunks(result_json: dict, citations_by_id: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    chunks = []
    meeting = result_json.get("meeting", {})
    if isinstance(meeting, dict):
        text = _metadata_text(
            {
                "title": meeting.get("title"),
                "startedAt": meeting.get("startedAt"),
                "durationSeconds": meeting.get("durationSeconds"),
                "meetingId": meeting.get("id"),
            },
            heading="Meeting metadata",
        )
        if text:
            chunks.append(
                _chunk(
                    chunk_id="meeting-metadata",
                    source_type="metadata",
                    section_type="meeting.metadata",
                    source_id=meeting.get("id") if isinstance(meeting.get("id"), str) else "meeting",
                    json_pointer="/meeting",
                    text=text,
                    citation_ids=[_json_citation_id("meeting-metadata")],
                    citations_by_id=citations_by_id,
                    embedding_provider=embedding_provider,
                    priority=SECTION_PRIORITY["meeting.metadata"],
                    title="Meeting metadata",
                )
            )
    return chunks


def _participant_chunks(result_json: dict, citations_by_id: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    participants = [item for item in result_json.get("participants", []) if isinstance(item, dict)]
    if not participants:
        return []
    chunks = []
    explicit_attendees = [item for item in participants if item.get("isAttendee") is True]
    speaker_profiles = [
        item
        for item in participants
        if str(item.get("subtype") or item.get("type") or "").casefold()
        == "speaker_profile"
    ]
    speakers = result_json.get("speakers")
    speaker_count = (
        speakers.get("speakerCount")
        if isinstance(speakers, dict)
        and isinstance(speakers.get("speakerCount"), int)
        and not isinstance(speakers.get("speakerCount"), bool)
        else None
    )
    ignored_segment_count = (
        int(speakers.get("ignoredSegmentCount") or 0)
        if isinstance(speakers, dict)
        else 0
    )
    speaker_count_exact = bool(
        isinstance(speakers, dict)
        and (
            speakers.get("speakerCountExact") is True
            or (
                "speakerCountExact" not in speakers
                and ignored_segment_count == 0
            )
        )
    )

    # The deterministic diarization aggregate owns global speaker
    # cardinality. Provider participant records may have incomplete attendee
    # flags or duplicate the same people under names and Speaker N aliases;
    # counting those flags created false 0-vs-N conflicts at verification.
    participant_count: int | None = None
    count_basis = "unresolved"
    attendee_sources: list[dict] = []
    if speaker_count is not None and speaker_count > 0 and speaker_count_exact:
        participant_count = speaker_count
        count_basis = "reliable_diarization_labels"
        attendee_sources = (
            explicit_attendees
            if len(explicit_attendees) == speaker_count
            else speaker_profiles
            if len(speaker_profiles) == speaker_count
            else []
        )
    elif speaker_count in (None, 0) and explicit_attendees:
        participant_count = len(explicit_attendees)
        count_basis = "explicit_attendee_records"
        attendee_sources = explicit_attendees
    elif participants and all(item.get("isMentionedOnly") is True for item in participants):
        participant_count = 0
        count_basis = "mentioned_only_records"

    attendee_names = [
        label
        for index, item in enumerate(attendee_sources, start=1)
        if (label := _record_label(item, index)) != f"Record {index}"
    ]
    overview = {
        "mentionedOnlyCount": len([item for item in participants if item.get("isMentionedOnly")]),
        "attendeeNames": attendee_names,
        "participants": [_record_label(item, index) for index, item in enumerate(participants, start=1)],
        "countBasis": count_basis,
    }
    if participant_count is not None:
        overview["participantCount"] = participant_count
    chunks.append(
        _chunk(
            chunk_id="participant-overview",
            source_type="structured",
            section_type="participant.overview",
            source_id="participant-overview",
            json_pointer="/participants",
            text=_metadata_text(overview, heading="Participant overview"),
            citation_ids=_overview_citation_ids(participants, result_json, citations_by_id),
            citations_by_id=citations_by_id,
            embedding_provider=embedding_provider,
            priority=SECTION_PRIORITY["participant.overview"],
            title="Participant overview",
            metadata={
                "recordType": "participant",
                "subtype": "overview",
                # The overview is a deterministic, meeting-local aggregate.
                # Giving it a stable record identity lets typed
                # ``search_records`` retrieve the exact participant count
                # instead of relying on semantic ranking to retain it.
                "recordId": "participant-overview",
                "recordFields": overview,
            },
        )
    )
    for index, participant in enumerate(participants, start=1):
        text = _metadata_text(participant, heading="Participant profile")
        if not _is_signal_text(text, min_tokens=1):
            continue
        chunks.append(
            _chunk(
                chunk_id=f"participant-profile-{index:03d}",
                source_type="structured",
                section_type="participant.profile",
                source_id=_record_id(participant, f"participant-{index:03d}"),
                json_pointer=f"/participants/{index - 1}",
                text=text,
                citation_ids=_structured_citation_ids(participant, result_json, citations_by_id),
                citations_by_id=citations_by_id,
                embedding_provider=embedding_provider,
                priority=SECTION_PRIORITY["participant.profile"],
                title=_record_label(participant, index),
            metadata={
                "recordType": "participant",
                "subtype": participant.get("subtype") or participant.get("type") or "profile",
                "recordId": participant.get("id"),
                "recordFields": participant,
                "evidenceRefs": participant.get("evidenceRefs", participant.get("citationIds", [])),
                "sourceRefs": participant.get("sourceRefs", participant.get("sourceWindowIds", [])),
                "derivedFrom": participant.get("derivedFrom", []),
            },
            )
        )
    return chunks


def _speaker_chunks(result_json: dict, citations_by_id: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    """Index the deterministic speaker aggregate retained by the v2 result."""
    speakers = result_json.get("speakers")
    if not isinstance(speakers, dict):
        return []
    text = _metadata_text(speakers, heading="Speaker statistics")
    if not _is_signal_text(text, min_tokens=1):
        return []
    return [
        _chunk(
            chunk_id="speaker-stats",
            source_type="structured",
            section_type="speaker.stats",
            source_id="speaker-stats",
            json_pointer="/speakers",
            text=text,
            citation_ids=[_json_citation_id("speaker-stats")],
            citations_by_id=citations_by_id,
            embedding_provider=embedding_provider,
            priority=SECTION_PRIORITY["speaker.stats"],
            title="Speaker statistics",
            metadata={"recordType": "speaker", "subtype": "statistics"},
        )
    ]


def _record_chunks(result_json: dict, citations_by_id: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    specs = [
        ("facts", "fact.record", "fact", "Fact"),
        ("events", "event.timeline", "event", "Event"),
        ("entities", "entity.profile", "entity", "Entity"),
        ("relationships", "relationship.edge", "relationship", "Relationship"),
        ("actions", "action.item", "action", "Action item"),
        ("decisions", "decision.record", "decision", "Decision"),
        ("risks", "risk.record", "risk", "Risk"),
        ("questions", "question.record", "question", "Question"),
        ("observations", "observation.record", "observation", "Observation"),
    ]
    chunks = []
    for section, default_section_type, source_type, heading in specs:
        values = [item for item in result_json.get(section, []) if isinstance(item, dict)]
        for index, item in enumerate(values, start=1):
            section_type = default_section_type
            if section == "facts" and (item.get("subtype") or item.get("type")) == "participant_count":
                section_type = "fact.participant_count"
            text = _metadata_text(item, heading=heading)
            if not _is_signal_text(text, min_tokens=1):
                continue
            chunks.append(
                _chunk(
                    chunk_id=f"{section_type.replace('.', '-')}-{index:03d}",
                    source_type="structured",
                    section_type=section_type,
                    source_id=_record_id(item, f"{source_type}-{index:03d}"),
                    json_pointer=f"/{section}/{index - 1}",
                    text=text,
                    citation_ids=_structured_citation_ids(item, result_json, citations_by_id),
                    citations_by_id=citations_by_id,
                    embedding_provider=embedding_provider,
                    priority=SECTION_PRIORITY.get(section_type, SECTION_PRIORITY[default_section_type]),
                    title=_record_label(item, index),
                    metadata={
                        "recordType": source_type,
                        "subtype": item.get("subtype") or item.get("type"),
                        "recordId": item.get("id"),
                        "recordFields": item,
                        "evidenceRefs": item.get("evidenceRefs", []),
                        "sourceRefs": item.get("sourceRefs", []),
                        "derivedFrom": item.get("derivedFrom", []),
                        "confidence": item.get("confidence"),
                    },
                )
            )
    return chunks


def _structured_citation_ids(item: dict, result_json: dict, citations_by_id: dict) -> list[str]:
    """Return direct citations or one stable citation for derived JSON records."""
    explicit = _citation_ids(item)
    if explicit:
        return explicit
    record_id = item.get("id") if isinstance(item.get("id"), str) else item.get("type", "record")
    return [_json_record_citation_id(str(record_id))]


def _overview_citation_ids(participants: list[dict], result_json: dict, citations_by_id: dict) -> list[str]:
    ids: list[str] = [_json_record_citation_id("participant-overview")]
    for participant in participants:
        ids.extend(_structured_citation_ids(participant, result_json, citations_by_id))
    return list(dict.fromkeys(ids))


def _json_citation_id(chunk_id: str) -> str:
    """Stable citation ID for authoritative JSON-only evidence without transcript ranges."""
    return f"json-{chunk_id}"


def _json_record_citation_id(record_id: str) -> str:
    """Stable citation ID for a derived/structured JSON record."""
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", record_id).strip("-") or "record"
    return f"json-record-{normalized}"


def _topic_chunks(result_json: dict, citations_by_id: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    chunks = []
    for index, topic in enumerate([item for item in result_json.get("topics", []) if isinstance(item, dict)], start=1):
        text = _metadata_text(topic, heading="Topic summary")
        if not _is_signal_text(text, min_tokens=2):
            continue
        chunks.append(
            _chunk(
                chunk_id=f"topic-summary-{index:03d}",
                source_type="structured",
                section_type="topic.summary",
                source_id=_record_id(topic, f"topic-{index:03d}"),
                json_pointer=f"/topics/{index - 1}",
                text=text,
                citation_ids=_citation_ids(topic),
                citations_by_id=citations_by_id,
                embedding_provider=embedding_provider,
                priority=SECTION_PRIORITY["topic.summary"],
                title=_record_label(topic, index),
                metadata={
                    "recordType": "topic",
                    "subtype": topic.get("subtype") or "summary",
                    "recordId": topic.get("id"),
                    "recordFields": topic,
                    "evidenceRefs": _citation_ids(topic),
                    "level": topic.get("level"),
                },
            )
        )
    return chunks


def _summary_chunks(result_json: dict, citations_by_id: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    summaries = result_json.get("summaries", {})
    if not isinstance(summaries, dict):
        return []
    chunks = []
    executive = summaries.get("executive", {})
    if isinstance(executive, dict) and executive.get("text"):
        chunks.append(
            _chunk(
                chunk_id="summary-executive",
                source_type="structured",
                section_type="summary.executive",
                source_id="summary-executive",
                json_pointer="/summaries/executive",
                text=_metadata_text(executive, heading="Executive summary"),
                citation_ids=_citation_ids(executive),
                citations_by_id=citations_by_id,
                embedding_provider=embedding_provider,
                priority=SECTION_PRIORITY["summary.executive"],
                title="Executive summary",
                metadata={
                    "evidenceEligible": bool(_citation_ids(executive)),
                    "lineageStatus": (
                        executive.get("lineageStatus")
                        or ("verified" if _citation_ids(executive) else "context_only")
                    ),
                },
            )
        )
    for key, section_type in (("topicLevel", "summary.topic"), ("timelineLevel", "summary.timeline")):
        values = _section_items(summaries.get(key, []))
        for index, item in enumerate(values, start=1):
            text = _metadata_text(item, heading=_labelize(section_type))
            if not _is_signal_text(text, min_tokens=2):
                continue
            chunks.append(
                _chunk(
                    chunk_id=f"{section_type.replace('.', '-')}-{index:03d}",
                    source_type="structured",
                    section_type=section_type,
                    source_id=_record_id(item, f"{section_type}-{index:03d}"),
                    json_pointer=f"/summaries/{key}/{index - 1}",
                    text=text,
                    citation_ids=_citation_ids(item),
                    citations_by_id=citations_by_id,
                    embedding_provider=embedding_provider,
                    priority=SECTION_PRIORITY[section_type],
                    title=_record_label(item, index),
                    metadata={"recordType": "summary"},
                )
            )
    return chunks


def _transcript_window_chunks(
    result_json: dict,
    citations_by_id: dict,
    embedding_provider: TextEmbeddingProvider,
) -> list[dict]:
    segments = [item for item in result_json.get("transcript", {}).get("segments", []) if isinstance(item, dict)]
    evidence_ids_by_segment: dict[str, list[str]] = {}
    for evidence_id, evidence in citations_by_id.items():
        for segment_id in evidence.get("segmentIds", []):
            if isinstance(segment_id, str):
                evidence_ids_by_segment.setdefault(segment_id, []).append(evidence_id)
    source_refs_by_segment: dict[str, list[str]] = {}
    for source_window in result_json.get("transcript", {}).get("windows", []):
        if not isinstance(source_window, dict) or not isinstance(source_window.get("id"), str):
            continue
        for segment_id in source_window.get("segmentIds", []):
            if isinstance(segment_id, str):
                source_refs_by_segment.setdefault(segment_id, []).append(source_window["id"])
    chunks = []
    window: list[tuple[int, dict]] = []
    for segment_index, segment in enumerate(segments):
        text = str(segment.get("text") or "").strip()
        if not _is_transcript_signal_text(text):
            continue
        window.append((segment_index, segment))
        if len(window) >= 3:
            chunks.append(
                _transcript_window_chunk(
                    window,
                    len(chunks) + 1,
                    citations_by_id,
                    evidence_ids_by_segment,
                    source_refs_by_segment,
                    embedding_provider,
                )
            )
            window = []
    if window:
        chunks.append(
            _transcript_window_chunk(
                window,
                len(chunks) + 1,
                citations_by_id,
                evidence_ids_by_segment,
                source_refs_by_segment,
                embedding_provider,
            )
        )
    return chunks


def _transcript_window_chunk(
    indexed_window: list[tuple[int, dict]],
    index: int,
    citations_by_id: dict,
    evidence_ids_by_segment: dict[str, list[str]],
    source_refs_by_segment: dict[str, list[str]],
    embedding_provider: TextEmbeddingProvider,
) -> dict:
    window = [item for _, item in indexed_window]
    segment_ids = [item.get("id") for item in window if isinstance(item.get("id"), str)]
    citation_ids = list(
        dict.fromkeys(
            evidence_id
            for segment_id in segment_ids
            for evidence_id in evidence_ids_by_segment.get(segment_id, [])
        )
    )
    source_refs = list(
        dict.fromkeys(
            source_ref
            for segment_id in segment_ids
            for source_ref in source_refs_by_segment.get(segment_id, [])
        )
    )
    start_ms = min([item.get("startMs") for item in window if isinstance(item.get("startMs"), int)] or [None])
    end_ms = max([item.get("endMs") for item in window if isinstance(item.get("endMs"), int)] or [None])
    text = _metadata_text(
        {
            "segments": [
                {
                    "speakerLabel": item.get("speakerLabel") or item.get("speaker"),
                    "startMs": item.get("startMs"),
                    "endMs": item.get("endMs"),
                    "confidence": item.get("confidence"),
                    "text": item.get("text"),
                }
                for item in window
            ]
        },
        heading="Transcript evidence window",
    )
    return _chunk(
        chunk_id=f"transcript-window-{index:03d}",
        source_type="transcript",
        section_type="transcript.window",
        source_id=f"transcript-window-{index:03d}",
        json_pointer=f"/transcript/segments/{indexed_window[0][0]}",
        text=text,
        citation_ids=citation_ids,
        citations_by_id=citations_by_id,
        embedding_provider=embedding_provider,
        priority=SECTION_PRIORITY["transcript.window"],
        title="Transcript evidence window",
        segment_ids=segment_ids,
        start_ms=start_ms,
        end_ms=end_ms,
        metadata={
            "recordType": "transcript",
            "subtype": "window",
            "evidenceRefs": citation_ids,
            "sourceRefs": source_refs,
            "recordFields": {"segmentIds": segment_ids},
        },
    )


def _chunk(
    *,
    chunk_id: str,
    source_type: str,
    section_type: str,
    source_id: str | None,
    json_pointer: str,
    text: str,
    citation_ids: list[str],
    citations_by_id: dict,
    embedding_provider: TextEmbeddingProvider,
    priority: int,
    title: str | None = None,
    segment_ids: list[str | None] | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
    metadata: dict | None = None,
) -> dict:
    resolved_segment_ids = []
    resolved_start = start_ms
    resolved_end = end_ms
    for citation_id in citation_ids:
        citation = citations_by_id.get(citation_id, {})
        resolved_segment_ids.extend(citation.get("segmentIds", []))
        citation_start = citation.get("startMs")
        citation_end = citation.get("endMs")
        if isinstance(citation_start, int | float):
            resolved_start = citation_start if resolved_start is None else min(resolved_start, citation_start)
        if isinstance(citation_end, int | float):
            resolved_end = citation_end if resolved_end is None else max(resolved_end, citation_end)
    if segment_ids:
        resolved_segment_ids.extend([segment_id for segment_id in segment_ids if segment_id])
    citation_quotes = {
        citation_id: str(citations_by_id.get(citation_id, {}).get("quote") or "")
        for citation_id in citation_ids
        if citations_by_id.get(citation_id, {}).get("quote")
    }
    citation_locations = {
        citation_id: {
            "segmentIds": list(citations_by_id.get(citation_id, {}).get("segmentIds") or []),
            "startMs": citations_by_id.get(citation_id, {}).get("startMs"),
            "endMs": citations_by_id.get(citation_id, {}).get("endMs"),
        }
        for citation_id in citation_ids
        if citation_id in citations_by_id
    }
    chunk_metadata = dict(metadata or {})
    chunk_metadata.setdefault("evidenceEligible", bool(citation_ids))
    if citation_quotes:
        chunk_metadata["citationQuotes"] = citation_quotes
    if citation_locations:
        chunk_metadata["citationLocations"] = citation_locations
    return {
        "chunkId": chunk_id,
        "sourceType": source_type,
        "sectionType": section_type,
        "sourceId": source_id,
        "jsonPointer": json_pointer,
        "text": text,
        "citationIds": citation_ids,
        "segmentIds": list(dict.fromkeys(resolved_segment_ids)),
        "startMs": resolved_start,
        "endMs": resolved_end,
        "tokenCount": len(_tokens(text)),
        "embedding": None,
        "visibility": "workspace",
        "metadata": {
            "title": title,
            "priority": priority,
            **chunk_metadata,
        },
    }
