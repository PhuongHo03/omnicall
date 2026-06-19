import re
import time

from sqlalchemy.orm import Session

from backend.models.meeting_models import MeetingIntelligenceResult
from backend.providers.embedding_provider import TextEmbeddingProvider, get_embedding_provider
from backend.providers.vector_provider import VectorProvider, VectorProviderError, get_vector_provider
from backend.repositories.meeting_repository import MeetingIntelligenceResultRepository
from backend.repositories.retrieval_repository import MeetingChunkRepository


STRUCTURED_SECTION_PRIORITY = {
    "summary.executive": 10,
    "summary.detailed": 20,
    "summary.keyPoints": 30,
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
    chunks.extend(_summary_chunks(result_json, citations_by_id, citations_by_segment_id, embedding_provider))
    chunks.extend(_analysis_chunks(result_json, citations_by_id, citations_by_segment_id, embedding_provider))
    chunks.extend(_transcript_fallback_chunks(result_json, embedding_provider))
    return chunks


def _summary_chunks(
    result_json: dict,
    citations_by_id: dict,
    citations_by_segment_id: dict,
    embedding_provider: TextEmbeddingProvider,
) -> list[dict]:
    summary = result_json.get("summary", {})
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
        if section_name == "emptySections" or not isinstance(values, list):
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


def _transcript_fallback_chunks(result_json: dict, embedding_provider: TextEmbeddingProvider) -> list[dict]:
    chunks = []
    for index, segment in enumerate(result_json.get("transcript", {}).get("segments", []), start=1):
        text = segment.get("text", "")
        if not _is_signal_text(text):
            continue
        segment_key = segment.get("id") or f"seg-{index:03d}"
        chunk = _chunk(
            chunk_id=f"transcript-{segment_key}",
            source_type="transcript",
            section_type="transcript.segment",
            source_id=segment_key,
            json_pointer=f"/transcript/segments/{index - 1}",
            text=text,
            citation_ids=[],
            citations_by_id={},
            citations_by_segment_id=None,
            embedding_provider=embedding_provider,
            priority=500,
            segment_ids=[segment.get("id")],
            start_ms=segment.get("startMs"),
            end_ms=segment.get("endMs"),
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
        },
    }


def _item_text(item: dict) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    for key in ("text", "summary", "task", "item", "decision", "note", "risk", "outcome", "question", "quote", "name", "description", "title"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


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
    for key in ("citationIds", "citations", "cites", "sourceSegmentIds", "segmentIds"):
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
    for key in ("title", "name", "owner", "type"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _is_signal_text(text: str, *, min_tokens: int = 3) -> bool:
    tokens = _tokens(text)
    return len(tokens) >= min_tokens


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\wÀ-ỹ]+", text, flags=re.UNICODE)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
