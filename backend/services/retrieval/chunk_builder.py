import re
import time
from collections.abc import Iterable

from backend.providers.embedding_provider import TextEmbeddingProvider
from backend.services.retrieval.section_registry import SECTION_TYPE_SET
from backend.services.retrieval.chunk_text import (
    citation_ids as _citation_ids,
    citations_by_id as _citations_by_id,
    elapsed_ms,
    format_ms as _format_ms,
    is_signal_text as _is_signal_text,
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
    result_json = _retrieval_view(result_json)
    citations_by_id = _citations_by_id(result_json)
    chunks: list[dict] = []
    chunks.extend(_metadata_chunks(result_json, citations_by_id, embedding_provider))
    chunks.extend(_speaker_chunks(result_json, citations_by_id, embedding_provider))
    chunks.extend(_participant_chunks(result_json, citations_by_id, embedding_provider))
    chunks.extend(_record_chunks(result_json, citations_by_id, embedding_provider))
    chunks.extend(_topic_chunks(result_json, citations_by_id, embedding_provider))
    chunks.extend(_summary_chunks(result_json, citations_by_id, embedding_provider))
    chunks.extend(_quality_chunks(result_json, citations_by_id, embedding_provider))
    chunks.extend(_evidence_chunks(result_json, citations_by_id, embedding_provider))
    chunks.extend(_transcript_window_chunks(result_json, embedding_provider))
    _attach_embeddings(chunks, embedding_provider)
    unknown_sections = {chunk.get("sectionType") for chunk in chunks} - SECTION_TYPE_SET
    if unknown_sections:
        raise ValueError(f"Retrieval builder emitted unregistered sections: {sorted(unknown_sections)}")
    return chunks


def _retrieval_view(result_json: dict) -> dict:
    """Expose unified records through the existing chunk builders."""
    knowledge = result_json.get("knowledge")
    if not isinstance(knowledge, dict):
        return result_json
    view = dict(result_json)
    sections = {section: [] for section in ("participants", "entities", "facts", "events", "topics", "actions", "decisions", "risks", "questions")}
    record_sections = {
        "participant": "participants",
        "entity": "entities",
        "fact": "facts",
        "event": "events",
        "topic": "topics",
        "action": "actions",
        "decision": "decisions",
        "risk": "risks",
        "question": "questions",
    }
    for record in knowledge.get("records", []):
        if not isinstance(record, dict):
            continue
        section = record_sections.get(record.get("type", ""))
        if section not in sections:
            continue
        item = dict(record.get("data", {}))
        item["id"] = record.get("id")
        item["citationIds"] = record.get("citationIds", [])
        item["sourceWindowIds"] = record.get("sourceWindowIds", [])
        item["confidence"] = record.get("confidence", item.get("confidence", 0.5))
        sections[section].append(item)
    view.update(sections)
    view["relationships"] = list(knowledge.get("relationships", []))
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
                    citation_ids=[],
                    citations_by_id=citations_by_id,
                    embedding_provider=embedding_provider,
                    priority=SECTION_PRIORITY["meeting.metadata"],
                    title="Meeting metadata",
                )
            )
    source = result_json.get("source", {})
    if isinstance(source, dict):
        text = _metadata_text(source, heading="Processing source")
        if text:
            chunks.append(
                _chunk(
                    chunk_id="source-processing",
                    source_type="metadata",
                    section_type="source.processing",
                    source_id="source-processing",
                    json_pointer="/source",
                    text=text,
                    citation_ids=[],
                    citations_by_id=citations_by_id,
                    embedding_provider=embedding_provider,
                    priority=SECTION_PRIORITY["source.processing"],
                    title="Processing source",
                )
            )
    coverage = result_json.get("transcript", {}).get("coverage", {})
    if isinstance(coverage, dict):
        text = _metadata_text(coverage, heading="Transcript coverage")
        if text:
            chunks.append(
                _chunk(
                    chunk_id="transcript-coverage",
                    source_type="metadata",
                    section_type="transcript.coverage",
                    source_id="transcript-coverage",
                    json_pointer="/transcript/coverage",
                    text=text,
                    citation_ids=[],
                    citations_by_id=citations_by_id,
                    embedding_provider=embedding_provider,
                    priority=SECTION_PRIORITY["transcript.coverage"],
                    title="Transcript coverage",
                )
            )
    return chunks


def _speaker_chunks(result_json: dict, citations_by_id: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    speakers = result_json.get("speakers", {})
    if not isinstance(speakers, dict):
        return []
    text = _metadata_text(speakers, heading="Speaker statistics")
    if not text:
        return []
    return [
        _chunk(
            chunk_id="speaker-stats",
            source_type="structured",
            section_type="speaker.stats",
            source_id="speaker-stats",
            json_pointer="/speakers",
            text=text,
            citation_ids=[],
            citations_by_id=citations_by_id,
            embedding_provider=embedding_provider,
            priority=SECTION_PRIORITY["speaker.stats"],
            title="Speaker statistics",
            metadata={
                "speakerCount": speakers.get("speakerCount"),
                "identifiedParticipantCount": speakers.get("identifiedParticipantCount"),
                "mentionedOnlyCount": speakers.get("mentionedOnlyCount"),
            },
        )
    ]


def _participant_chunks(result_json: dict, citations_by_id: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    participants = [item for item in result_json.get("participants", []) if isinstance(item, dict)]
    if not participants:
        return []
    chunks = []
    overview = {
        "participantCount": len([item for item in participants if item.get("isAttendee")]),
        "mentionedOnlyCount": len([item for item in participants if item.get("isMentionedOnly")]),
        "participants": [_record_label(item, index) for index, item in enumerate(participants, start=1)],
    }
    chunks.append(
        _chunk(
            chunk_id="participant-overview",
            source_type="structured",
            section_type="participant.overview",
            source_id="participant-overview",
            json_pointer="/participants",
            text=_metadata_text(overview, heading="Participant overview"),
            citation_ids=[],
            citations_by_id=citations_by_id,
            embedding_provider=embedding_provider,
            priority=SECTION_PRIORITY["participant.overview"],
            title="Participant overview",
            metadata=overview,
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
                citation_ids=_citation_ids(participant),
                citations_by_id=citations_by_id,
                embedding_provider=embedding_provider,
                priority=SECTION_PRIORITY["participant.profile"],
                title=_record_label(participant, index),
                metadata={"recordType": "participant"},
            )
        )
    return chunks


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
    ]
    chunks = []
    for section, default_section_type, source_type, heading in specs:
        values = [item for item in result_json.get(section, []) if isinstance(item, dict)]
        for index, item in enumerate(values, start=1):
            section_type = default_section_type
            if section == "facts" and item.get("type") == "participant_count":
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
                    citation_ids=_citation_ids(item),
                    citations_by_id=citations_by_id,
                    embedding_provider=embedding_provider,
                    priority=SECTION_PRIORITY.get(section_type, SECTION_PRIORITY[default_section_type]),
                    title=_record_label(item, index),
                    metadata={"recordType": source_type, "recordId": item.get("id"), "confidence": item.get("confidence")},
                )
            )
    return chunks


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
                metadata={"recordType": "topic", "level": topic.get("level")},
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


def _quality_chunks(result_json: dict, citations_by_id: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    chunks = []
    for section, heading, pointer in (("quality", "Quality overview", "/quality"), ("extraction", "Extraction overview", "/extraction")):
        value = result_json.get(section, {})
        if not isinstance(value, dict):
            continue
        overview = {key: item for key, item in value.items() if key not in {"warnings", "unsupportedClaims"}}
        text = _metadata_text(overview, heading=heading)
        section_type = f"{section}.overview"
        if text:
            chunks.append(
                _chunk(
                    chunk_id=f"{section}-overview",
                    source_type="metadata",
                    section_type=section_type,
                    source_id=f"{section}-overview",
                    json_pointer=pointer,
                    text=text,
                    citation_ids=[],
                    citations_by_id=citations_by_id,
                    embedding_provider=embedding_provider,
                    priority=SECTION_PRIORITY.get(section_type, 200),
                    title=heading,
                )
            )
        for index, warning in enumerate(_section_items(value.get("warnings", [])), start=1):
            warning_text = _metadata_text(warning, heading=f"{heading} warning")
            if _is_signal_text(warning_text, min_tokens=1):
                chunks.append(
                    _chunk(
                        chunk_id=f"{section}-warning-{index:03d}",
                        source_type="metadata",
                        section_type=f"{section}.warning",
                        source_id=f"{section}-warning-{index:03d}",
                        json_pointer=f"{pointer}/warnings/{index - 1}",
                        text=warning_text,
                        citation_ids=[],
                        citations_by_id=citations_by_id,
                        embedding_provider=embedding_provider,
                        priority=SECTION_PRIORITY.get(f"{section}.warning", 201),
                        title=f"{heading} warning",
                    )
                )
    return chunks


def _evidence_chunks(result_json: dict, citations_by_id: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    citations = list(citations_by_id.values())
    if not citations:
        return []
    starts = [item.get("startMs") for item in citations if isinstance(item.get("startMs"), int | float)]
    ends = [item.get("endMs") for item in citations if isinstance(item.get("endMs"), int | float)]
    text = _metadata_text(
        {
            "citationCount": len(citations),
            "referencedSegmentCount": len({segment_id for citation in citations for segment_id in citation.get("segmentIds", [])}),
            "firstEvidenceTime": _format_ms(min(starts)) if starts else None,
            "lastEvidenceTime": _format_ms(max(ends)) if ends else None,
        },
        heading="Evidence map",
    )
    return [
        _chunk(
            chunk_id="evidence-map",
            source_type="metadata",
            section_type="evidence.map",
            source_id="evidence-map",
            json_pointer="/evidence/citations",
            text=text,
            citation_ids=[],
            citations_by_id=citations_by_id,
            embedding_provider=embedding_provider,
            priority=SECTION_PRIORITY["evidence.map"],
            title="Evidence map",
        )
    ]


def _transcript_window_chunks(result_json: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    segments = [item for item in result_json.get("transcript", {}).get("segments", []) if isinstance(item, dict)]
    chunks = []
    window: list[dict] = []
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        if not _is_signal_text(text):
            continue
        window.append(segment)
        if len(window) >= 3:
            chunks.append(_transcript_window_chunk(window, len(chunks) + 1, embedding_provider))
            window = []
    if window:
        chunks.append(_transcript_window_chunk(window, len(chunks) + 1, embedding_provider))
    return chunks


def _transcript_window_chunk(window: list[dict], index: int, embedding_provider: TextEmbeddingProvider) -> dict:
    segment_ids = [item.get("id") for item in window if isinstance(item.get("id"), str)]
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
        json_pointer=f"/transcript/segments/{max(0, index - 1)}",
        text=text,
        citation_ids=[],
        citations_by_id={},
        embedding_provider=embedding_provider,
        priority=SECTION_PRIORITY["transcript.window"],
        title="Transcript evidence window",
        segment_ids=segment_ids,
        start_ms=start_ms,
        end_ms=end_ms,
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
        resolved_start = citation.get("startMs", resolved_start)
        resolved_end = citation.get("endMs", resolved_end)
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


def _legacy_citations_by_id(result_json: dict) -> dict[str, dict]:
    citations = result_json.get("evidence", {}).get("citations", [])
    if not isinstance(citations, list):
        return {}
    return {
        citation["id"]: citation
        for citation in citations
        if isinstance(citation, dict) and isinstance(citation.get("id"), str)
    }


def _legacy_citation_ids(item: object) -> list[str]:
    if not isinstance(item, dict):
        return []
    value = item.get("citationIds")
    return [entry for entry in value if isinstance(entry, str)] if isinstance(value, list) else []


def _legacy_record_id(item: dict, fallback: str) -> str:
    value = item.get("id")
    return value if isinstance(value, str) and value else fallback


def _legacy_record_label(item: dict, index: int) -> str:
    for key in ("title", "displayName", "name", "task", "text", "type", "id"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"Record {index}"


def _legacy_section_items(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [value]
    if isinstance(value, dict):
        return [value]
    return []


def _legacy_metadata_text(value: object, *, heading: str | None = None) -> str:
    parts: list[str] = []
    if heading:
        parts.append(heading)
    parts.extend(_flatten_metadata(value))
    return ". ".join(part for part in parts if part).strip()


def _legacy_flatten_metadata(value: object, *, prefix: str | None = None, depth: int = 0) -> list[str]:
    if depth > 4 or value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        return [f"{_labelize(prefix)}: {stripped}" if prefix else stripped]
    if isinstance(value, bool | int | float):
        return [f"{_labelize(prefix)}: {value}" if prefix else str(value)]
    if isinstance(value, list):
        return _flatten_list(value, prefix=prefix, depth=depth)
    if isinstance(value, dict):
        flattened = []
        for key in _ordered_keys(value):
            if key in {"embedding"}:
                continue
            nested_prefix = key if prefix is None else f"{prefix} {key}"
            flattened.extend(_flatten_metadata(value.get(key), prefix=nested_prefix, depth=depth + 1))
        return flattened
    return [f"{_labelize(prefix)}: {value}" if prefix else str(value)]


def _legacy_flatten_list(value: Iterable, *, prefix: str | None, depth: int) -> list[str]:
    flattened = []
    scalar_values = [str(item).strip() for item in value if isinstance(item, str | bool | int | float) and str(item).strip()]
    if scalar_values:
        flattened.append(f"{_labelize(prefix)}: {_join_values(scalar_values)}" if prefix else _join_values(scalar_values))
    for index, item in enumerate(value):
        if isinstance(item, dict):
            nested_prefix = f"{prefix} {index + 1}" if prefix else f"item {index + 1}"
            flattened.extend(_flatten_metadata(item, prefix=nested_prefix, depth=depth + 1))
    return flattened


def _legacy_ordered_keys(value: dict) -> list[str]:
    preferred = [
        "id",
        "type",
        "title",
        "displayName",
        "normalizedName",
        "label",
        "speakerLabel",
        "speakerLabels",
        "role",
        "organization",
        "subject",
        "predicate",
        "value",
        "unit",
        "task",
        "ownerParticipantId",
        "ownerName",
        "status",
        "priority",
        "dueAt",
        "occurredAt",
        "startMs",
        "endMs",
        "confidence",
        "description",
        "summary",
        "text",
        "quote",
        "citationIds",
        "segmentIds",
        "participantIds",
        "entityIds",
        "factIds",
        "eventIds",
        "topicIds",
    ]
    keys = [key for key in preferred if key in value]
    keys.extend(key for key in value.keys() if key not in keys)
    return keys


def _legacy_labelize(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).replace("_", " ").replace("-", " ")


def _legacy_join_values(value: object) -> str:
    if not isinstance(value, list):
        return str(value)
    return ", ".join(str(item) for item in value if item is not None)


def _legacy_format_ms(value: object) -> str:
    if not isinstance(value, int | float) or value < 0:
        return "unknown time"
    total_seconds = int(value / 1000)
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"


def _legacy_is_signal_text(text: str, *, min_tokens: int = 3) -> bool:
    return len(_tokens(text)) >= min_tokens


def _legacy_tokens(text: str) -> list[str]:
    return re.findall(r"[\wÀ-ỹ]+", text, flags=re.UNICODE)


def _legacy_elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
