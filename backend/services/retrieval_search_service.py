import math
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.models.meeting_models import MeetingChunkRecord
from backend.providers.embedding_provider import LocalHashEmbeddingProvider, get_embedding_provider
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
        embedding_provider: LocalHashEmbeddingProvider | None = None,
        vector_provider: VectorProvider | None = None,
    ) -> None:
        self.chunks = MeetingChunkRepository(session)
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.vector_provider = vector_provider or get_vector_provider()

    def search_meeting(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        query: str,
        limit: int = 6,
    ) -> list[RetrievedChunk]:
        query_embedding = self.embedding_provider.embed_text(query).vector
        vector_hits = self._search_vector_index(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            query=query,
            query_embedding=query_embedding,
            limit=limit,
        )
        if vector_hits is not None:
            return vector_hits
        return self._search_postgres_fallback(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            query=query,
            query_embedding=query_embedding,
            limit=limit,
        )

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
        query_tokens = set(_meaningful_tokens(query))
        # The local hash embedding is deterministic but not semantically rich. Revalidate
        # vector hits against authoritative PostgreSQL text so unrelated questions do not
        # inherit plausible-looking Milvus neighbors.
        if getattr(self.embedding_provider, "provider_name", "") == "local-hash-embedding":
            records = [
                record
                for record in records
                if _has_meaningful_overlap(query_tokens, record.text)
            ]
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


def _score_chunk(*, chunk: MeetingChunkRecord, query_embedding: list[float], query_tokens: set[str]) -> float:
    chunk_tokens = set(_meaningful_tokens(chunk.text))
    lexical = len(query_tokens.intersection(chunk_tokens)) / max(1, min(len(query_tokens), 8))
    vector = chunk.embedding if isinstance(chunk.embedding, list) else []
    cosine = max(0.0, _cosine_similarity(query_embedding, vector))
    base = (0.65 * lexical) + (0.35 * cosine)
    priority_bonus = max(0.0, (500 - _priority(chunk)) / 5000)
    return round(base + priority_bonus, 6)


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
