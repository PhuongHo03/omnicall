import math
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.configs.settings import Settings, get_settings
from backend.models.meeting_models import MeetingChunkRecord
from backend.providers.embedding_provider import TextEmbeddingProvider, get_embedding_provider
from backend.providers.rerank_provider import RerankProvider, RerankProviderError, get_rerank_provider
from backend.providers.vector_provider import VectorProvider, VectorProviderError, get_vector_provider
from backend.repositories.retrieval_repository import MeetingChunkRepository


@dataclass(frozen=True)
class RetrievedChunk:
    record: MeetingChunkRecord
    score: float


class RetrievalSearchService:
    def __init__(
        self,
        session: Session,
        embedding_provider: TextEmbeddingProvider | None = None,
        vector_provider: VectorProvider | None = None,
        rerank_provider: RerankProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.chunks = MeetingChunkRepository(session)
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.vector_provider = vector_provider or get_vector_provider()
        self.rerank_provider = rerank_provider or get_rerank_provider(self.settings)
        self.last_rerank_metadata: dict = {}

    def search_meeting(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        query: str,
        limit: int = 6,
    ) -> list[RetrievedChunk]:
        query_embedding = self.embedding_provider.embed_text(query).vector
        candidate_limit = max(limit, self.settings.rerank_top_k)
        output_limit = min(limit, self.settings.rerank_output_k)
        vector_hits = self._search_vector_index(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            query=query,
            query_embedding=query_embedding,
            limit=candidate_limit,
        )
        candidates = vector_hits
        if candidates is None:
            candidates = self._search_postgres_fallback(
                workspace_id=workspace_id,
                meeting_id=meeting_id,
                query=query,
                query_embedding=query_embedding,
                limit=candidate_limit,
            )
        pinned = self._intent_pinned_chunks(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            query=query,
            limit=output_limit,
        )
        reranked = self._rerank(query=query, candidates=candidates, output_limit=output_limit)
        if pinned:
            self.last_rerank_metadata = {
                **self.last_rerank_metadata,
                "intentPinnedCount": len(pinned),
            }
        return _merge_unique_chunks(pinned, reranked, output_limit)

    def _search_vector_index(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        query: str,
        query_embedding: list[float],
        limit: int,
    ) -> list[RetrievedChunk] | None:
        if not self.vector_provider.enabled:
            return None
        try:
            hits = self.vector_provider.search_chunk_ids(
                workspace_id=workspace_id,
                meeting_id=meeting_id,
                query_vector=query_embedding,
                limit=limit,
            )
        except VectorProviderError:
            return None
        if not hits:
            return None
        records = self.chunks.list_by_chunk_ids_for_workspace_meeting(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            chunk_ids=[hit.chunk_id for hit in hits],
        )
        score_by_chunk_id = {hit.chunk_id: hit.score for hit in hits}
        return [
            RetrievedChunk(record=record, score=score_by_chunk_id.get(record.chunk_id, 0.0))
            for record in records
        ]

    def _search_postgres_fallback(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        query: str,
        query_embedding: list[float],
        limit: int,
    ) -> list[RetrievedChunk]:
        query_tokens = set(_meaningful_tokens(query))
        scored: list[RetrievedChunk] = []
        for chunk in self.chunks.list_for_workspace_meeting(workspace_id=workspace_id, meeting_id=meeting_id):
            if not _has_meaningful_overlap(query_tokens, chunk.text):
                continue
            score = _score_chunk(
                chunk=chunk,
                query_embedding=query_embedding,
                query_tokens=query_tokens,
            )
            if score >= 0.18:
                scored.append(RetrievedChunk(record=chunk, score=score))
        scored.sort(key=lambda item: (-item.score, _priority(item.record), item.record.created_at))
        return scored[:limit]

    def _rerank(self, *, query: str, candidates: list[RetrievedChunk], output_limit: int) -> list[RetrievedChunk]:
        if not candidates:
            self.last_rerank_metadata = {
                "provider": self.rerank_provider.provider_name,
                "model": self.rerank_provider.model_name,
                "inputCount": 0,
                "outputCount": 0,
            }
            return []
        try:
            reranked = self.rerank_provider.rerank(query=query, chunks=candidates, output_k=output_limit)
        except RerankProviderError as exc:
            fallback = candidates[:output_limit]
            self.last_rerank_metadata = {
                "provider": self.rerank_provider.provider_name,
                "model": self.rerank_provider.model_name,
                "status": "unavailable",
                "error": str(exc),
                "inputCount": len(candidates),
                "outputCount": len(fallback),
            }
            return fallback
        self.last_rerank_metadata = {
            "provider": self.rerank_provider.provider_name,
            "model": self.rerank_provider.model_name,
            "status": "reranked",
            "inputCount": len(candidates),
            "outputCount": len(reranked),
        }
        return reranked

    def _intent_pinned_chunks(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        query: str,
        limit: int,
    ) -> list[RetrievedChunk]:
        section_types = _intent_section_types(query)
        if not section_types:
            return []
        order = {section_type: index for index, section_type in enumerate(section_types)}
        chunks = [
            chunk
            for chunk in self.chunks.list_for_workspace_meeting(workspace_id=workspace_id, meeting_id=meeting_id)
            if chunk.source_type == "structured" and chunk.section_type in order
        ]
        chunks.sort(key=lambda chunk: (order[chunk.section_type], _priority(chunk), chunk.created_at))
        return [RetrievedChunk(record=chunk, score=1.0) for chunk in chunks[:limit]]


def _score_chunk(*, chunk: MeetingChunkRecord, query_embedding: list[float], query_tokens: set[str]) -> float:
    chunk_tokens = set(_meaningful_tokens(chunk.text))
    lexical = len(query_tokens.intersection(chunk_tokens)) / max(1, min(len(query_tokens), 8))
    vector = chunk.embedding if isinstance(chunk.embedding, list) else []
    cosine = max(0.0, _cosine_similarity(query_embedding, vector))
    base = (0.65 * lexical) + (0.35 * cosine)
    priority_bonus = max(0.0, (500 - _priority(chunk)) / 5000)
    return round(base + priority_bonus, 6)


def _merge_unique_chunks(left: list[RetrievedChunk], right: list[RetrievedChunk], limit: int) -> list[RetrievedChunk]:
    merged: list[RetrievedChunk] = []
    seen: set[str] = set()
    for item in [*left, *right]:
        if item.record.chunk_id in seen:
            continue
        seen.add(item.record.chunk_id)
        merged.append(item)
        if len(merged) >= limit:
            break
    return merged


def _intent_section_types(query: str) -> list[str]:
    tokens = set(_meaningful_tokens(query))
    normalized = " ".join(_tokens(query))

    if tokens.intersection({"summary", "summarize", "overview", "topic", "topics", "main", "point", "points"}):
        return ["summary.executive", "summary.detailed", "summary.keyPoints", "analysis.topics"]
    if _contains_any(normalized, ["tom tat", "tóm tắt", "tong ket", "tổng kết", "y chinh", "ý chính", "noi dung", "nội dung", "ban ve", "bàn về", "van de", "vấn đề", "chu de", "chủ đề"]):
        return ["summary.executive", "summary.detailed", "summary.keyPoints", "analysis.topics"]

    if tokens.intersection({"reason", "reasons", "cause", "causes", "because", "why"}):
        return ["summary.detailed", "summary.executive", "analysis.requirements", "analysis.constraints", "analysis.blockers", "summary.keyPoints"]
    if _contains_any(normalized, ["tai sao", "tại sao", "vi sao", "vì sao", "ly do", "lý do", "nguyen nhan", "nguyên nhân", "do dau", "do đâu"]):
        return ["summary.detailed", "summary.executive", "analysis.requirements", "analysis.constraints", "analysis.blockers", "summary.keyPoints"]

    if tokens.intersection({"return", "returns", "refund", "exchange", "process", "policy", "procedure"}):
        return ["summary.detailed", "analysis.requirements", "analysis.constraints", "analysis.blockers", "analysis.followUps", "summary.keyPoints"]
    if _contains_any(normalized, ["doi tra", "đổi trả", "tra hang", "trả hàng", "hoan tien", "hoàn tiền", "nhu nao", "như nào", "the nao", "thế nào", "cach", "cách", "quy trinh", "quy trình"]):
        return ["summary.detailed", "analysis.requirements", "analysis.constraints", "analysis.blockers", "analysis.followUps", "summary.keyPoints"]

    if tokens.intersection({"action", "actions", "task", "tasks", "todo", "followup", "followups"}):
        return ["analysis.actionItems", "analysis.followUps", "analysis.decisions"]
    if _contains_any(normalized, ["viec can lam", "việc cần làm", "can lam", "cần làm", "nhiem vu", "nhiệm vụ", "hanh dong", "hành động", "follow up", "theo doi", "theo dõi"]):
        return ["analysis.actionItems", "analysis.followUps", "analysis.decisions"]

    if tokens.intersection({"risk", "risks", "blocker", "blockers"}):
        return ["analysis.risks", "analysis.blockers", "analysis.openQuestions"]
    if _contains_any(normalized, ["rui ro", "rủi ro", "van de can luu y", "vấn đề cần lưu ý", "can luu y", "cần lưu ý", "tro ngai", "trở ngại"]):
        return ["analysis.risks", "analysis.blockers", "analysis.openQuestions", "analysis.importantNotes"]

    if tokens.intersection({"decision", "decisions", "decide", "outcome", "outcomes"}):
        return ["analysis.decisions", "analysis.outcomes", "analysis.openQuestions"]
    if _contains_any(normalized, ["quyet dinh", "quyết định", "ket qua", "kết quả", "thong nhat", "thống nhất"]):
        return ["analysis.decisions", "analysis.outcomes", "analysis.openQuestions"]

    if tokens.intersection({"timeline", "deadline", "date", "dates", "time"}):
        return ["analysis.timeline", "analysis.followUps", "summary.keyPoints"]
    if _contains_any(normalized, ["moc thoi gian", "mốc thời gian", "thoi han", "thời hạn", "deadline", "khi nao", "khi nào"]):
        return ["analysis.timeline", "analysis.followUps", "summary.keyPoints"]

    return []


def _contains_any(text: str, phrases: list[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _priority(chunk: MeetingChunkRecord) -> int:
    value = (chunk.metadata_json or {}).get("priority", 500)
    return value if isinstance(value, int) else 500


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\wÀ-ỹ]+", text.lower(), flags=re.UNICODE)


def _meaningful_tokens(text: str) -> list[str]:
    return [
        token
        for token in _tokens(text)
        if len(token) >= 2 and token not in _STOPWORDS
    ]


def _has_meaningful_overlap(query_tokens: set[str], text: str) -> bool:
    if not query_tokens:
        return False
    return bool(query_tokens.intersection(_meaningful_tokens(text)))


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "was",
    "what",
    "when",
    "where",
    "who",
    "why",
    "with",
    "about",
    "có",
    "của",
    "cho",
    "câu",
    "cuộc",
    "gì",
    "hỏi",
    "không",
    "là",
    "nào",
    "nói",
    "trong",
    "về",
    "và",
}
