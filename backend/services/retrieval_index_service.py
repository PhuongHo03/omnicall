import re
import time

from sqlalchemy.orm import Session

from backend.models.meeting_models import MeetingIntelligenceResult
from backend.providers.embedding_provider import TextEmbeddingProvider, get_embedding_provider
from backend.providers.vector_provider import VectorProvider, VectorProviderError, get_vector_provider
from backend.repositories.meeting_repository import MeetingIntelligenceResultRepository
from backend.repositories.retrieval_repository import MeetingChunkRepository


STRUCTURED_SECTION_PRIORITY = {
    "meeting.metadata": 5,
    "summary.executive": 10,
    "summary.detailed": 20,
    "summary.keyPoints": 30,
    "participants.overview": 32,
    "participants.participant": 34,
    "source.processing": 35,
    "source.voiceMetadata": 36,
    "source.guardrails": 37,
    "analysis.decisions": 40,
    "analysis.actionItems": 50,
    "analysis.importantNotes": 60,
    "analysis.timeline": 70,
    "analysis.risks": 80,
    "analysis.blockers": 90,
    "analysis.dependencies": 100,
    "analysis.followUps": 110,
    "analysis.openQuestions": 120,
    "analysis.topics": 130,
    "analysis.entities": 140,
    "analysis.importantQuotes": 150,
    "analysis.metrics": 160,
    "analysis.glossary": 170,
    "analysis.emptySections": 180,
    "quality.overview": 190,
    "quality.warning": 191,
    "transcript.coverage": 195,
    "citations.map": 450,
}


class RetrievalIndexService:
    def __init__(
        self,
        session: Session,
        embedding_provider: TextEmbeddingProvider | None = None,
        vector_provider: VectorProvider | None = None,
    ) -> None:
        self.session = session
        self.results = MeetingIntelligenceResultRepository(session)
        self.chunks = MeetingChunkRepository(session)
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.vector_provider = vector_provider or get_vector_provider()
        self.last_vector_metadata: dict = {}
        self.last_index_metadata: dict = {}

    def rebuild_for_latest_result(self, meeting_id: str) -> list[dict]:
        result = self.results.get_latest_for_meeting(meeting_id)
        if result is None:
            return []
        return self.rebuild_for_result(result)

    def rebuild_for_result(self, result: MeetingIntelligenceResult) -> list[dict]:
        embedding_started = time.perf_counter()
        chunk_dicts = build_retrieval_chunks(result.result_json, embedding_provider=self.embedding_provider)
        embedding_duration_ms = _elapsed_ms(embedding_started)
        records = self.chunks.replace_for_result(
            meeting_id=result.meeting_id,
            intelligence_result_id=result.id,
            chunks=chunk_dicts,
        )
        vector_started = time.perf_counter()
        self.last_vector_metadata = self._upsert_vectors(records)
        vector_duration_ms = _elapsed_ms(vector_started)
        self.last_index_metadata = {
            "chunkCount": len(records),
            "embeddingProvider": self.embedding_provider.provider_name,
            "embeddingModel": self.embedding_provider.model_name,
            "embeddingDurationMs": embedding_duration_ms,
            "vectorProvider": self.vector_provider.provider_name,
            "vectorDurationMs": vector_duration_ms,
            "vector": self.last_vector_metadata,
        }
        return [
            {
                "id": record.id,
                "chunkId": record.chunk_id,
                "sourceType": record.source_type,
                "sectionType": record.section_type,
                "jsonPointer": record.json_pointer,
            }
            for record in records
        ]

    def _upsert_vectors(self, records: list) -> dict:
        try:
            return self.vector_provider.upsert_chunks(records)
        except VectorProviderError as exc:
            return {
                "provider": self.vector_provider.provider_name,
                "status": "failed",
                "error": str(exc),
                "chunkCount": len(records),
            }


def build_retrieval_chunks(result_json: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    citations_by_id = {citation.get("id"): citation for citation in result_json.get("citations", [])}
    citations_by_segment_id = {
        segment_id: citation
        for citation in result_json.get("citations", [])
        for segment_id in citation.get("segmentIds", [])
        if isinstance(segment_id, str)
    }
    chunks: list[dict] = []
    chunks.extend(_meeting_chunks(result_json, embedding_provider))
    chunks.extend(_source_chunks(result_json, embedding_provider))
    chunks.extend(_participant_chunks(result_json, citations_by_id, citations_by_segment_id, embedding_provider))
    chunks.extend(_summary_chunks(result_json, citations_by_id, citations_by_segment_id, embedding_provider))
    chunks.extend(_analysis_chunks(result_json, citations_by_id, citations_by_segment_id, embedding_provider))
    chunks.extend(_transcript_coverage_chunks(result_json, embedding_provider))
    chunks.extend(_quality_chunks(result_json, embedding_provider))
    chunks.extend(_citation_map_chunks(result_json, embedding_provider))
    chunks.extend(_transcript_fallback_chunks(result_json, embedding_provider))
    return chunks


def _meeting_chunks(result_json: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    meeting = result_json.get("meeting", {})
    if not isinstance(meeting, dict):
        return []
    text = _metadata_text(
        {
            "title": meeting.get("title"),
            "language": meeting.get("language"),
            "startedAt": meeting.get("startedAt"),
            "durationSeconds": meeting.get("durationSeconds"),
            "meetingId": meeting.get("id"),
        },
        heading="Meeting metadata",
    )
    if not text:
        return []
    return [
        _chunk(
            chunk_id="meeting-metadata",
            source_type="metadata",
            section_type="meeting.metadata",
            source_id=meeting.get("id") if isinstance(meeting.get("id"), str) else "meeting",
            json_pointer="/meeting",
            text=text,
            citation_ids=[],
            citations_by_id={},
            citations_by_segment_id=None,
            embedding_provider=embedding_provider,
            priority=STRUCTURED_SECTION_PRIORITY["meeting.metadata"],
            title="Meeting metadata",
            metadata={"rawSection": "meeting"},
        )
    ]


def _source_chunks(result_json: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    source = result_json.get("source", {})
    if not isinstance(source, dict):
        return []
    chunks = []
    processing_keys = (
        "assetIds",
        "assetObjectKeys",
        "analysisProvider",
        "analysisModel",
        "llmProvider",
        "transcriptionProvider",
        "transcriptionModel",
        "generatedAt",
    )
    processing_text = _metadata_text(
        {key: source.get(key) for key in processing_keys if key in source},
        heading="Processing source",
    )
    if processing_text:
        chunks.append(
            _chunk(
                chunk_id="source-processing",
                source_type="metadata",
                section_type="source.processing",
                source_id="source-processing",
                json_pointer="/source",
                text=processing_text,
                citation_ids=[],
                citations_by_id={},
                citations_by_segment_id=None,
                embedding_provider=embedding_provider,
                priority=STRUCTURED_SECTION_PRIORITY["source.processing"],
                title="Processing source",
                metadata={"rawSection": "source"},
            )
        )
    voice_metadata = source.get("voiceMetadata")
    if isinstance(voice_metadata, dict):
        voice_text = _metadata_text(voice_metadata, heading="Voice processing metadata")
        if voice_text:
            chunks.append(
                _chunk(
                    chunk_id="source-voice-metadata",
                    source_type="metadata",
                    section_type="source.voiceMetadata",
                    source_id="source-voiceMetadata",
                    json_pointer="/source/voiceMetadata",
                    text=voice_text,
                    citation_ids=[],
                    citations_by_id={},
                    citations_by_segment_id=None,
                    embedding_provider=embedding_provider,
                    priority=STRUCTURED_SECTION_PRIORITY["source.voiceMetadata"],
                    title="Voice processing metadata",
                    metadata={"rawSection": "source.voiceMetadata"},
                )
            )
    guardrails = source.get("guardrails")
    if isinstance(guardrails, dict):
        guardrail_text = _metadata_text(guardrails, heading="Guardrail metadata")
        if guardrail_text:
            chunks.append(
                _chunk(
                    chunk_id="source-guardrails",
                    source_type="metadata",
                    section_type="source.guardrails",
                    source_id="source-guardrails",
                    json_pointer="/source/guardrails",
                    text=guardrail_text,
                    citation_ids=[],
                    citations_by_id={},
                    citations_by_segment_id=None,
                    embedding_provider=embedding_provider,
                    priority=STRUCTURED_SECTION_PRIORITY["source.guardrails"],
                    title="Guardrail metadata",
                    metadata={"rawSection": "source.guardrails"},
                )
            )
    return chunks


def _participant_chunks(
    result_json: dict,
    citations_by_id: dict,
    citations_by_segment_id: dict,
    embedding_provider: TextEmbeddingProvider,
) -> list[dict]:
    participants = result_json.get("participants", [])
    if not isinstance(participants, list) or not participants:
        return []
    chunks = []
    names = [
        _participant_name(participant, index)
        for index, participant in enumerate(participants, start=1)
        if isinstance(participant, dict)
    ]
    overview_text = _metadata_text(
        {
            "participantCount": len(names),
            "participants": names,
        },
        heading="Participants overview",
    )
    if overview_text:
        chunks.append(
            _chunk(
                chunk_id="participants-overview",
                source_type="structured",
                section_type="participants.overview",
                source_id="participants-overview",
                json_pointer="/participants",
                text=overview_text,
                citation_ids=[],
                citations_by_id=citations_by_id,
                citations_by_segment_id=citations_by_segment_id,
                embedding_provider=embedding_provider,
                priority=STRUCTURED_SECTION_PRIORITY["participants.overview"],
                title="Participants overview",
                metadata={"participantCount": len(names)},
            )
        )
    for index, participant in enumerate(participants, start=1):
        if not isinstance(participant, dict):
            continue
        text = _item_text(participant)
        if not _is_signal_text(text, min_tokens=1):
            continue
        reference_ids = _item_references(participant)
        citation_ids, segment_ids = _split_references(reference_ids, citations_by_id)
        chunks.append(
            _chunk(
                chunk_id=f"participants.participant-{index:03d}",
                source_type="structured",
                section_type="participants.participant",
                source_id=_item_id(participant) or _participant_name(participant, index),
                json_pointer=f"/participants/{index - 1}",
                text=text,
                citation_ids=citation_ids,
                citations_by_id=citations_by_id,
                citations_by_segment_id=citations_by_segment_id,
                embedding_provider=embedding_provider,
                priority=STRUCTURED_SECTION_PRIORITY["participants.participant"],
                title=_participant_name(participant, index),
                segment_ids=segment_ids,
                metadata={"rawSection": "participants"},
            )
        )
    return chunks


def _summary_chunks(
    result_json: dict,
    citations_by_id: dict,
    citations_by_segment_id: dict,
    embedding_provider: TextEmbeddingProvider,
) -> list[dict]:
    summary = result_json.get("summary", {})
    if not isinstance(summary, dict):
        return []
    chunks = []
    if summary.get("executive"):
        chunks.append(
            _chunk(
                chunk_id="summary-executive",
                source_type="structured",
                section_type="summary.executive",
                source_id="summary-executive",
                json_pointer="/summary/executive",
                text=summary["executive"],
                citation_ids=[],
                citations_by_id=citations_by_id,
                citations_by_segment_id=citations_by_segment_id,
                embedding_provider=embedding_provider,
                priority=STRUCTURED_SECTION_PRIORITY["summary.executive"],
            )
        )
    for section_name in ("detailed", "keyPoints"):
        values = _section_items(summary.get(section_name, []))
        for index, item in enumerate(values, start=1):
            text = _item_text(item)
            if not _is_signal_text(text, min_tokens=2):
                continue
            section_type = f"summary.{section_name}"
            reference_ids = _item_references(item)
            citation_ids, segment_ids = _split_references(reference_ids, citations_by_id)
            chunks.append(
                _chunk(
                    chunk_id=f"{section_type}-{index:03d}",
                    source_type="structured",
                    section_type=section_type,
                    source_id=_item_id(item) or f"{section_type}-{index:03d}",
                    json_pointer=f"/summary/{section_name}/{index - 1}",
                    text=text,
                    citation_ids=citation_ids,
                    citations_by_id=citations_by_id,
                    citations_by_segment_id=citations_by_segment_id,
                    embedding_provider=embedding_provider,
                    priority=STRUCTURED_SECTION_PRIORITY[section_type],
                    title=_item_title(item),
                    segment_ids=segment_ids,
                )
            )
    return chunks


def _analysis_chunks(
    result_json: dict,
    citations_by_id: dict,
    citations_by_segment_id: dict,
    embedding_provider: TextEmbeddingProvider,
) -> list[dict]:
    analysis = result_json.get("analysis", {})
    chunks = []
    for section_name, values in analysis.items():
        if section_name == "emptySections":
            chunks.extend(_empty_section_chunks(values, embedding_provider))
            continue
        if not isinstance(values, list):
            continue
        section_type = f"analysis.{section_name}"
        priority = STRUCTURED_SECTION_PRIORITY.get(section_type, 200)
        for index, item in enumerate(_section_items(values), start=1):
            text = _item_text(item)
            if not _is_signal_text(text, min_tokens=2):
                continue
            reference_ids = _item_references(item)
            citation_ids, segment_ids = _split_references(reference_ids, citations_by_id)
            chunks.append(
                _chunk(
                    chunk_id=f"{section_type}-{index:03d}",
                    source_type="structured",
                    section_type=section_type,
                    source_id=_item_id(item) or f"{section_type}-{index:03d}",
                    json_pointer=f"/analysis/{section_name}/{index - 1}",
                    text=text,
                    citation_ids=citation_ids,
                    citations_by_id=citations_by_id,
                    citations_by_segment_id=citations_by_segment_id,
                    embedding_provider=embedding_provider,
                    priority=priority,
                    title=_item_title(item),
                    segment_ids=segment_ids,
                )
            )
    return chunks


def _empty_section_chunks(value: object, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    items: list[tuple[str, object]] = []
    if isinstance(value, dict):
        items = [(str(key), reason) for key, reason in value.items()]
    elif isinstance(value, list):
        items = [(str(item), "No evidence was found for this section.") for item in value]
    chunks = []
    for index, (section_name, reason) in enumerate(items, start=1):
        text = _metadata_text(
            {
                "section": section_name,
                "reason": reason,
            },
            heading="Empty analysis section",
        )
        if not _is_signal_text(text, min_tokens=2):
            continue
        chunks.append(
            _chunk(
                chunk_id=f"analysis.emptySections-{index:03d}",
                source_type="structured",
                section_type="analysis.emptySections",
                source_id=section_name,
                json_pointer=f"/analysis/emptySections/{_json_pointer_key(section_name)}",
                text=text,
                citation_ids=[],
                citations_by_id={},
                citations_by_segment_id=None,
                embedding_provider=embedding_provider,
                priority=STRUCTURED_SECTION_PRIORITY["analysis.emptySections"],
                title=section_name,
                metadata={"emptySection": section_name},
            )
        )
    return chunks


def _transcript_coverage_chunks(result_json: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    coverage = result_json.get("transcript", {}).get("coverage", {})
    if not isinstance(coverage, dict):
        return []
    text = _metadata_text(coverage, heading="Transcript coverage")
    if not text:
        return []
    return [
        _chunk(
            chunk_id="transcript-coverage",
            source_type="metadata",
            section_type="transcript.coverage",
            source_id="transcript-coverage",
            json_pointer="/transcript/coverage",
            text=text,
            citation_ids=[],
            citations_by_id={},
            citations_by_segment_id=None,
            embedding_provider=embedding_provider,
            priority=STRUCTURED_SECTION_PRIORITY["transcript.coverage"],
            title="Transcript coverage",
            metadata={"rawSection": "transcript.coverage"},
        )
    ]


def _quality_chunks(result_json: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    quality = result_json.get("quality", {})
    if not isinstance(quality, dict):
        return []
    chunks = []
    overview = {
        key: value
        for key, value in quality.items()
        if key != "warnings"
    }
    overview_text = _metadata_text(overview, heading="Quality overview")
    if overview_text:
        chunks.append(
            _chunk(
                chunk_id="quality-overview",
                source_type="metadata",
                section_type="quality.overview",
                source_id="quality-overview",
                json_pointer="/quality",
                text=overview_text,
                citation_ids=[],
                citations_by_id={},
                citations_by_segment_id=None,
                embedding_provider=embedding_provider,
                priority=STRUCTURED_SECTION_PRIORITY["quality.overview"],
                title="Quality overview",
                metadata={"rawSection": "quality"},
            )
        )
    warnings = quality.get("warnings", [])
    for index, warning in enumerate(_section_items(warnings), start=1):
        text = _item_text(warning) if isinstance(warning, dict) else str(warning).strip()
        if not _is_signal_text(text, min_tokens=1):
            continue
        chunks.append(
            _chunk(
                chunk_id=f"quality.warning-{index:03d}",
                source_type="metadata",
                section_type="quality.warning",
                source_id=f"quality.warning-{index:03d}",
                json_pointer=f"/quality/warnings/{index - 1}",
                text=f"Quality warning: {text}",
                citation_ids=[],
                citations_by_id={},
                citations_by_segment_id=None,
                embedding_provider=embedding_provider,
                priority=STRUCTURED_SECTION_PRIORITY["quality.warning"],
                title="Quality warning",
                metadata={"rawSection": "quality.warnings"},
            )
        )
    return chunks


def _citation_map_chunks(result_json: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    citations = result_json.get("citations", [])
    if not isinstance(citations, list) or not citations:
        return []
    segment_ids = []
    starts = []
    ends = []
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        segment_ids.extend(item for item in citation.get("segmentIds", []) if isinstance(item, str))
        if isinstance(citation.get("startMs"), int | float):
            starts.append(citation["startMs"])
        if isinstance(citation.get("endMs"), int | float):
            ends.append(citation["endMs"])
    text = _metadata_text(
        {
            "citationCount": len(citations),
            "referencedSegmentCount": len(set(segment_ids)),
            "firstEvidenceTime": _format_ms(min(starts)) if starts else None,
            "lastEvidenceTime": _format_ms(max(ends)) if ends else None,
        },
        heading="Citation map",
    )
    if not text:
        return []
    return [
        _chunk(
            chunk_id="citations-map",
            source_type="metadata",
            section_type="citations.map",
            source_id="citations-map",
            json_pointer="/citations",
            text=text,
            citation_ids=[],
            citations_by_id={},
            citations_by_segment_id=None,
            embedding_provider=embedding_provider,
            priority=STRUCTURED_SECTION_PRIORITY["citations.map"],
            title="Citation map",
            metadata={"rawSection": "citations"},
        )
    ]


def _transcript_fallback_chunks(result_json: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    chunks = []
    for index, segment in enumerate(result_json.get("transcript", {}).get("segments", []), start=1):
        if not isinstance(segment, dict):
            continue
        text = segment.get("text", "")
        if not _is_signal_text(text):
            continue
        segment_key = segment.get("id") or f"seg-{index:03d}"
        enriched_text = _metadata_text(
            {
                "speaker": segment.get("speaker"),
                "startMs": segment.get("startMs"),
                "endMs": segment.get("endMs"),
                "confidence": segment.get("confidence"),
                "text": text,
            },
            heading="Transcript segment",
        )
        chunk = _chunk(
            chunk_id=f"transcript-{segment_key}",
            source_type="transcript",
            section_type="transcript.segment",
            source_id=segment_key,
            json_pointer=f"/transcript/segments/{index - 1}",
            text=enriched_text or text,
            citation_ids=[],
            citations_by_id={},
            citations_by_segment_id=None,
            embedding_provider=embedding_provider,
            priority=500,
            segment_ids=[segment.get("id")],
            start_ms=segment.get("startMs"),
            end_ms=segment.get("endMs"),
            metadata={
                "speaker": segment.get("speaker"),
                "confidence": segment.get("confidence"),
            },
        )
        chunks.append(chunk)
    return chunks


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
    citations_by_segment_id: dict | None,
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
        if citations_by_segment_id:
            for segment_id in segment_ids:
                citation = citations_by_segment_id.get(segment_id)
                if citation:
                    resolved_start = citation.get("startMs", resolved_start)
                    resolved_end = citation.get("endMs", resolved_end)
    embedding = embedding_provider.embed_text(text)
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
        "embedding": embedding.vector,
        "visibility": "workspace",
        "metadata": {
            "title": title,
            "priority": priority,
            "embeddingProvider": embedding.provider_name,
            "embeddingModel": embedding.model_name,
            **(metadata or {}),
        },
    }


def _item_text(item: object) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    return _metadata_text(item)


def _section_items(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [value]
    if isinstance(value, dict):
        return [value]
    return []


def _item_references(item: object) -> list[str]:
    if not isinstance(item, dict):
        return []
    for key in ("citationIds", "citations", "cites", "sourceSegmentIds", "segmentIds", "references", "referenceIds"):
        value = item.get(key)
        if isinstance(value, list):
            return [entry for entry in value if isinstance(entry, str)]
    return []


def _split_references(reference_ids: list[str], citations_by_id: dict) -> tuple[list[str], list[str]]:
    citation_ids: list[str] = []
    segment_ids: list[str] = []
    for reference_id in reference_ids:
        if reference_id in citations_by_id:
            citation_ids.append(reference_id)
        else:
            segment_ids.append(reference_id)
    return citation_ids, segment_ids


def _item_id(item: object) -> str | None:
    if not isinstance(item, dict):
        return None
    value = item.get("id")
    return value if isinstance(value, str) and value else None


def _item_title(item: object) -> str | None:
    if not isinstance(item, dict):
        return None
    for key in ("title", "name", "speaker", "owner", "assignee", "role", "type"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _participant_name(participant: dict, index: int) -> str:
    for key in ("name", "speaker", "displayName", "label"):
        value = participant.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"Participant {index}"


def _metadata_text(value: object, *, heading: str | None = None) -> str:
    parts: list[str] = []
    if heading:
        parts.append(heading)
    parts.extend(_flatten_metadata(value))
    return ". ".join(part for part in parts if part).strip()


def _flatten_metadata(value: object, *, prefix: str | None = None, depth: int = 0) -> list[str]:
    if depth > 4:
        return []
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        return [f"{_labelize(prefix)}: {stripped}" if prefix else stripped]
    if isinstance(value, bool | int | float):
        return [f"{_labelize(prefix)}: {value}" if prefix else str(value)]
    if isinstance(value, list):
        flattened = []
        scalar_values = [
            str(item).strip()
            for item in value
            if isinstance(item, str | bool | int | float) and str(item).strip()
        ]
        if scalar_values:
            flattened.append(f"{_labelize(prefix)}: {_join_values(scalar_values)}" if prefix else _join_values(scalar_values))
        for index, item in enumerate(value):
            if isinstance(item, dict):
                nested_prefix = f"{prefix} {index + 1}" if prefix else f"item {index + 1}"
                flattened.extend(_flatten_metadata(item, prefix=nested_prefix, depth=depth + 1))
        return flattened
    if isinstance(value, dict):
        flattened = []
        for key in _ordered_keys(value):
            if key in {"embedding"}:
                continue
            nested = value.get(key)
            nested_prefix = key if prefix is None else f"{prefix} {key}"
            flattened.extend(_flatten_metadata(nested, prefix=nested_prefix, depth=depth + 1))
        return flattened
    return [f"{_labelize(prefix)}: {value}" if prefix else str(value)]


def _ordered_keys(value: dict) -> list[str]:
    preferred = [
        "title",
        "name",
        "speaker",
        "role",
        "owner",
        "assignee",
        "status",
        "priority",
        "dueDate",
        "deadline",
        "type",
        "category",
        "confidence",
        "details",
        "description",
        "summary",
        "text",
        "task",
        "item",
        "decision",
        "note",
        "risk",
        "outcome",
        "question",
        "quote",
        "citationIds",
        "sourceSegmentIds",
        "segmentIds",
        "references",
    ]
    keys = [key for key in preferred if key in value]
    keys.extend(key for key in value.keys() if key not in keys)
    return keys


def _labelize(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).replace("_", " ").replace("-", " ")


def _json_pointer_key(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _join_values(value: object) -> str:
    if not isinstance(value, list):
        return str(value)
    return ", ".join(str(item) for item in value if item is not None)


def _format_ms(value: object) -> str:
    if not isinstance(value, int | float) or value < 0:
        return "unknown time"
    total_seconds = int(value / 1000)
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"


def _is_signal_text(text: str, *, min_tokens: int = 3) -> bool:
    tokens = _tokens(text)
    return len(tokens) >= min_tokens


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\wÀ-ỹ]+", text, flags=re.UNICODE)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
