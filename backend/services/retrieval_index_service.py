import re

from sqlalchemy.orm import Session

from backend.models.meeting_models import MeetingIntelligenceResult
from backend.providers.embedding_provider import LocalHashEmbeddingProvider, get_embedding_provider
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
        embedding_provider: LocalHashEmbeddingProvider | None = None,
        vector_provider: VectorProvider | None = None,
    ) -> None:
        self.session = session
        self.results = MeetingIntelligenceResultRepository(session)
        self.chunks = MeetingChunkRepository(session)
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.vector_provider = vector_provider or get_vector_provider()
        self.last_vector_metadata: dict = {}

    def rebuild_for_latest_result(self, meeting_id: str) -> list[dict]:
        result = self.results.get_latest_for_meeting(meeting_id)
        if result is None:
            return []
        return self.rebuild_for_result(result)

    def rebuild_for_result(self, result: MeetingIntelligenceResult) -> list[dict]:
        chunk_dicts = build_retrieval_chunks(result.result_json, embedding_provider=self.embedding_provider)
        records = self.chunks.replace_for_result(
            workspace_id=result.workspace_id,
            meeting_id=result.meeting_id,
            intelligence_result_id=result.id,
            chunks=chunk_dicts,
        )
        self.last_vector_metadata = self._upsert_vectors(records)
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


def build_retrieval_chunks(result_json: dict, embedding_provider: LocalHashEmbeddingProvider) -> list[dict]:
    citations_by_id = {citation.get("id"): citation for citation in result_json.get("citations", [])}
    chunks: list[dict] = []
    chunks.extend(_summary_chunks(result_json, citations_by_id, embedding_provider))
    chunks.extend(_analysis_chunks(result_json, citations_by_id, embedding_provider))
    chunks.extend(_transcript_fallback_chunks(result_json, embedding_provider))
    return chunks


def _summary_chunks(result_json: dict, citations_by_id: dict, embedding_provider: LocalHashEmbeddingProvider) -> list[dict]:
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
                embedding_provider=embedding_provider,
                priority=STRUCTURED_SECTION_PRIORITY["summary.executive"],
            )
        )
    for section_name in ("detailed", "keyPoints"):
        for index, item in enumerate(summary.get(section_name, []), start=1):
            if not isinstance(item, dict):
                continue
            text = _item_text(item)
            if not _is_signal_text(text):
                continue
            section_type = f"summary.{section_name}"
            chunks.append(
                _chunk(
                    chunk_id=f"{section_type}-{index:03d}",
                    source_type="structured",
                    section_type=section_type,
                    source_id=item.get("id") or f"{section_type}-{index:03d}",
                    json_pointer=f"/summary/{section_name}/{index - 1}",
                    text=text,
                    citation_ids=item.get("citationIds", []),
                    citations_by_id=citations_by_id,
                    embedding_provider=embedding_provider,
                    priority=STRUCTURED_SECTION_PRIORITY[section_type],
                    title=item.get("title"),
                )
            )
    return chunks


def _analysis_chunks(result_json: dict, citations_by_id: dict, embedding_provider: LocalHashEmbeddingProvider) -> list[dict]:
    analysis = result_json.get("analysis", {})
    chunks = []
    for section_name, values in analysis.items():
        if section_name == "emptySections" or not isinstance(values, list):
            continue
        section_type = f"analysis.{section_name}"
        priority = STRUCTURED_SECTION_PRIORITY.get(section_type, 200)
        for index, item in enumerate(values, start=1):
            if not isinstance(item, dict):
                continue
            text = _item_text(item)
            if not _is_signal_text(text):
                continue
            chunks.append(
                _chunk(
                    chunk_id=f"{section_type}-{index:03d}",
                    source_type="structured",
                    section_type=section_type,
                    source_id=item.get("id") or f"{section_type}-{index:03d}",
                    json_pointer=f"/analysis/{section_name}/{index - 1}",
                    text=text,
                    citation_ids=item.get("citationIds", []),
                    citations_by_id=citations_by_id,
                    embedding_provider=embedding_provider,
                    priority=priority,
                    title=item.get("title") or item.get("name") or item.get("owner"),
                )
            )
    return chunks


def _transcript_fallback_chunks(result_json: dict, embedding_provider: LocalHashEmbeddingProvider) -> list[dict]:
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
    embedding_provider: LocalHashEmbeddingProvider,
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
    if not isinstance(item, dict):
        return str(item) if isinstance(item, str) else ""
    for key in ("text", "summary", "task", "question", "quote", "name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _is_signal_text(text: str) -> bool:
    tokens = _tokens(text)
    return len(tokens) >= 3


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\wÀ-ỹ]+", text, flags=re.UNICODE)
