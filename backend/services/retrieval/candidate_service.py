"""Candidate retrieval, intent pinning, and reranking coordination."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from backend.configs.settings import Settings
from backend.models.meeting_models import MeetingChunkRecord
from backend.providers.rerank_provider import RerankProvider, RerankProviderError
from backend.providers.vector_provider import VectorProvider, VectorProviderError
from backend.repositories.retrieval_repository import MeetingChunkRepository
from backend.services.retrieval.models import RetrievedChunk


@dataclass(frozen=True)
class RetrievalScoring:
    """Scoring policy injected by the retrieval orchestration boundary."""

    score_chunk: Callable[..., float]
    meaningful_tokens: Callable[[str], list[str]]
    has_meaningful_overlap: Callable[[set[str], str], bool]
    priority: Callable[[MeetingChunkRecord], int]
    intent_section_types: Callable[[str], list[str]]
    pin_relevance: Callable[[str, MeetingChunkRecord], float]


class RetrievalCandidateService:
    """Resolve vector/PostgreSQL candidates and apply ranking policies."""

    def __init__(
        self,
        *,
        chunks: MeetingChunkRepository,
        vector_provider: VectorProvider,
        rerank_provider: RerankProvider,
        settings: Settings,
        scoring: RetrievalScoring,
    ) -> None:
        self.chunks = chunks
        self.vector_provider = vector_provider
        self.rerank_provider = rerank_provider
        self.settings = settings
        self.scoring = scoring
        self.last_rerank_metadata: dict = {}
        self.last_postgres_metadata: dict = {}

    def vector_candidates(
        self, *, meeting_id: str, query: str = "", query_embedding: list[float], limit: int
    ) -> list[RetrievedChunk] | None:
        if not self.vector_provider.enabled:
            return None
        try:
            hits = self.vector_provider.search_chunk_ids(
                meeting_id=meeting_id,
                query_vector=query_embedding, limit=limit,
            )
        except VectorProviderError:
            return None
        if not hits:
            return None
        records = self.chunks.list_by_chunk_ids_for_meeting(
            meeting_id=meeting_id,
            chunk_ids=[hit.chunk_id for hit in hits],
        )
        hit_by_chunk_id = {hit.chunk_id: hit for hit in hits}
        valid_records = []
        for record in records:
            hit = hit_by_chunk_id.get(record.chunk_id)
            expected_generation = (record.metadata_json or {}).get("indexGeneration")
            if hit is None:
                continue
            if hit.generation is not None and expected_generation != hit.generation:
                continue
            valid_records.append(RetrievedChunk(record=record, score=hit.score))
        return valid_records

    def postgres_candidates(
        self, *, meeting_id: str, query: str, query_embedding: list[float], limit: int
    ) -> list[RetrievedChunk]:
        query_tokens = set(self.scoring.meaningful_tokens(query))
        all_chunks = self.chunks.list_for_meeting(meeting_id)
        trigram = self.chunks.search_by_trigram(
            meeting_id=meeting_id,
            query=query,
            threshold=self.settings.retrieval_trigram_threshold,
            limit=self.settings.retrieval_fallback_candidate_limit,
        )
        trigram_by_id = {record.chunk_id: score for record, score in trigram}
        structured = sorted(
            (
                chunk for chunk in all_chunks
                if chunk.source_type in {"structured", "metadata"}
            ),
            key=lambda chunk: (self.scoring.priority(chunk), chunk.created_at),
        )[: self.settings.retrieval_fallback_candidate_limit]
        candidate_records = {chunk.chunk_id: chunk for chunk in structured}
        candidate_records.update({record.chunk_id: record for record, _ in trigram})
        lexical_records = {
            chunk.chunk_id: chunk
            for chunk in all_chunks
            if self.scoring.has_meaningful_overlap(query_tokens, chunk.text)
        }
        candidate_records.update({
            chunk.chunk_id: chunk
            for chunk in lexical_records.values()
        })
        self.last_postgres_metadata = {
            "lexicalCount": len(lexical_records),
            "trigramCount": len(trigram),
            "structuredCount": len(structured),
            "candidatePoolCount": len(candidate_records),
        }
        scored: list[RetrievedChunk] = []
        for chunk_id, chunk in candidate_records.items():
            has_overlap = self.scoring.has_meaningful_overlap(query_tokens, chunk.text)
            trigram_score = trigram_by_id.get(chunk_id, 0.0)
            if not has_overlap and not trigram_score:
                continue
            score = self.scoring.score_chunk(
                chunk=chunk, query_embedding=query_embedding, query_tokens=query_tokens
            )
            if trigram_score:
                score = max(score, round(0.18 + (trigram_score * 0.35), 6))
            if score >= 0.18:
                scored.append(RetrievedChunk(record=chunk, score=score))
        scored.sort(key=lambda item: (-item.score, self.scoring.priority(item.record), item.record.created_at))
        return scored[:limit]

    def rerank(self, *, query: str, candidates: list[RetrievedChunk], output_limit: int) -> list[RetrievedChunk]:
        if not candidates:
            self.last_rerank_metadata = {
                "provider": self.rerank_provider.provider_name,
                "model": self.rerank_provider.model_name,
                "inputCount": 0, "outputCount": 0,
            }
            return []
        try:
            reranked = self.rerank_provider.rerank(query=query, chunks=candidates, output_k=output_limit)
        except RerankProviderError as exc:
            fallback = candidates[:output_limit]
            self.last_rerank_metadata = {
                "provider": self.rerank_provider.provider_name,
                "model": self.rerank_provider.model_name,
                "status": "unavailable", "error": str(exc),
                "inputCount": len(candidates), "outputCount": len(fallback),
            }
            return fallback
        self.last_rerank_metadata = {
            "provider": self.rerank_provider.provider_name,
            "model": self.rerank_provider.model_name,
            "status": "reranked", "inputCount": len(candidates), "outputCount": len(reranked),
        }
        return reranked

    def intent_pinned(
        self, *, meeting_id: str, query: str, limit: int
    ) -> list[RetrievedChunk]:
        section_types = self.scoring.intent_section_types(query)
        if not section_types:
            return []
        order = {section_type: index for index, section_type in enumerate(section_types)}
        chunks = [
            chunk for chunk in self.chunks.list_for_meeting(meeting_id)
            if chunk.source_type in {"structured", "metadata"} and chunk.section_type in order
        ]
        chunks.sort(key=lambda chunk: (
            order[chunk.section_type], -self.scoring.pin_relevance(query, chunk),
            self.scoring.priority(chunk), chunk.created_at
        ))
        return [RetrievedChunk(record=chunk, score=1.0) for chunk in chunks[:limit]]
