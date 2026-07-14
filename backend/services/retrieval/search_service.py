import math
import re
import time

from sqlalchemy.orm import Session

from backend.configs.settings import Settings, get_settings
from backend.models.meeting_models import MeetingChunkRecord
from backend.providers.embedding_provider import EmbeddingProviderError, TextEmbeddingProvider, get_embedding_provider
from backend.providers.rerank_provider import RerankProvider, RerankProviderError, get_rerank_provider
from backend.providers.vector_provider import VectorProvider, VectorProviderError, get_vector_provider
from backend.repositories.retrieval_repository import MeetingChunkRepository
from backend.services.retrieval.models import RetrievedChunk
from backend.services.retrieval.candidate_service import RetrievalCandidateService, RetrievalScoring


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
        self.last_search_metadata: dict = {}
        self.candidates = RetrievalCandidateService(
            chunks=self.chunks,
            vector_provider=self.vector_provider,
            rerank_provider=self.rerank_provider,
            settings=self.settings,
            scoring=RetrievalScoring(
                score_chunk=_score_chunk,
                meaningful_tokens=_meaningful_tokens,
                has_meaningful_overlap=_has_meaningful_overlap,
                priority=_priority,
                intent_section_types=_intent_section_types,
                pin_relevance=_pin_relevance,
            ),
        )

    def search_meeting(
        self,
        *,
        meeting_id: str,
        query: str,
        limit: int = 6,
    ) -> list[RetrievedChunk]:
        self._sync_candidates()
        search_started = time.perf_counter()
        embedding_started = time.perf_counter()
        embedding_error = None
        try:
            query_embedding = self.embedding_provider.embed_text(query).vector
        except EmbeddingProviderError as exc:
            query_embedding = []
            embedding_error = str(exc)
        embedding_duration_ms = _elapsed_ms(embedding_started)
        candidate_limit = max(limit, self.settings.rerank_top_k)
        output_limit = min(limit, self.settings.rerank_output_k)
        retrieval_started = time.perf_counter()
        self.candidates.last_postgres_metadata = {}
        if embedding_error:
            candidates = None
            retrieval_source = "postgres-fallback-embedding"
        else:
            candidates = self.candidates.vector_candidates(
                meeting_id=meeting_id,
                query=query,
                query_embedding=query_embedding,
                limit=candidate_limit,
            )
            retrieval_source = self.vector_provider.provider_name
        if candidates is None:
            if not embedding_error:
                retrieval_source = "postgres-fallback"
            candidates = self.candidates.postgres_candidates(
                meeting_id=meeting_id,
                query=query,
                query_embedding=query_embedding,
                limit=candidate_limit,
            )
        candidates, stale_chunk_count, legacy_chunk_count = _filter_embedding_generation(
            candidates,
            expected_identity=_embedding_identity(self.embedding_provider),
        )
        retrieval_duration_ms = _elapsed_ms(retrieval_started)
        pinned = self.candidates.intent_pinned(
            meeting_id=meeting_id,
            query=query,
            limit=output_limit,
        )
        pinned, pinned_stale_count, pinned_legacy_count = _filter_embedding_generation(
            pinned,
            expected_identity=_embedding_identity(self.embedding_provider),
        )
        stale_chunk_count += pinned_stale_count
        legacy_chunk_count += pinned_legacy_count
        rerank_started = time.perf_counter()
        reranked = self.candidates.rerank(query=query, candidates=candidates, output_limit=output_limit)
        self.last_rerank_metadata = self.candidates.last_rerank_metadata
        rerank_duration_ms = _elapsed_ms(rerank_started)
        if pinned:
            self.last_rerank_metadata = {
                **self.last_rerank_metadata,
                "intentPinnedCount": len(pinned),
            }
        result = _merge_unique_chunks(pinned, reranked, output_limit)
        self.last_search_metadata = {
            "embedding": {
                "provider": self.embedding_provider.provider_name,
                "model": self.embedding_provider.model_name,
                "durationMs": embedding_duration_ms,
                "dimensions": len(query_embedding),
                "status": "failed" if embedding_error else "succeeded",
                "error": embedding_error,
                "contractVersion": getattr(self.embedding_provider, "contract_version", "v1"),
                "identity": _embedding_identity(self.embedding_provider),
            },
            "retrieval": {
                "provider": retrieval_source,
                "configuredProvider": self.vector_provider.provider_name,
                "durationMs": retrieval_duration_ms,
                "candidateCount": len(candidates),
                "candidateLimit": candidate_limit,
                "staleEmbeddingCount": stale_chunk_count,
                "legacyEmbeddingCount": legacy_chunk_count,
                **self.candidates.last_postgres_metadata,
            },
            "rerank": {
                **self.last_rerank_metadata,
                "durationMs": rerank_duration_ms,
            },
            "resultCount": len(result),
            "durationMs": _elapsed_ms(search_started),
        }
        return result

    def _sync_candidates(self) -> None:
        """Keep runtime provider/repository overrides authoritative."""
        self.candidates.chunks = self.chunks
        self.candidates.vector_provider = self.vector_provider
        self.candidates.rerank_provider = self.rerank_provider
        self.candidates.settings = self.settings

    def _search_vector_index(
        self,
        *,
        meeting_id: str,
        query: str,
        query_embedding: list[float],
        limit: int,
    ) -> list[RetrievedChunk] | None:
        if not self.vector_provider.enabled:
            return None
        try:
            hits = self.vector_provider.search_chunk_ids(
                meeting_id=meeting_id,
                query_vector=query_embedding,
                limit=limit,
            )
        except VectorProviderError:
            return None
        if not hits:
            return None
        records = self.chunks.list_by_chunk_ids_for_meeting(
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
        meeting_id: str,
        query: str,
        query_embedding: list[float],
        limit: int,
    ) -> list[RetrievedChunk]:
        query_tokens = set(_meaningful_tokens(query))
        scored: list[RetrievedChunk] = []
        for chunk in self.chunks.list_for_meeting(meeting_id):
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
            for chunk in self.chunks.list_for_meeting(meeting_id)
            if chunk.source_type in {"structured", "metadata"} and chunk.section_type in order
        ]
        chunks.sort(key=lambda chunk: (order[chunk.section_type], -_pin_relevance(query, chunk), _priority(chunk), chunk.created_at))
        return [RetrievedChunk(record=chunk, score=1.0) for chunk in chunks[:limit]]


def _score_chunk(*, chunk: MeetingChunkRecord, query_embedding: list[float], query_tokens: set[str]) -> float:
    chunk_tokens = set(_meaningful_tokens(chunk.text))
    lexical = len(query_tokens.intersection(chunk_tokens)) / max(1, min(len(query_tokens), 8))
    vector = chunk.embedding if isinstance(chunk.embedding, list) else []
    cosine = max(0.0, _cosine_similarity(query_embedding, vector))
    base = (0.65 * lexical) + (0.35 * cosine)
    priority_bonus = max(0.0, (500 - _priority(chunk)) / 5000)
    return round(base + priority_bonus, 6)


def _pin_relevance(query: str, chunk: MeetingChunkRecord) -> float:
    query_tokens = set(_meaningful_tokens(query))
    text = chunk.text.lower()
    chunk_tokens = set(_meaningful_tokens(text))
    score = len(query_tokens.intersection(chunk_tokens))
    normalized = " ".join(_tokens(query))
    if _contains_any(normalized, ["quoc tich", "quốc tịch", "cong dan", "công dân", "nationality", "citizenship", "citizen"]):
        if _contains_any(text, ["citizen", "citizenship", "nationality", "united states", "u.s.", "usa", "american", "mỹ", "my"]):
            score += 10
    if _contains_any(normalized, ["tuoi", "tuổi", "age", "old"]):
        if _contains_any(text, ["age", "years old", "tuổi"]):
            score += 10
    if _contains_any(normalized, ["dia chi", "địa chỉ", "address"]):
        if _contains_any(text, ["address", "drive", "street", "city", "zip"]):
            score += 10
    if _contains_any(normalized, ["bang", "bằng", "degree", "certificate", "certification", "education"]):
        if _contains_any(text, ["degree", "ged", "certificate", "certification", "education"]):
            score += 10
    return float(score)


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


def _embedding_identity(provider) -> str:
    dimensions = getattr(provider, "expected_dimensions", None)
    if not isinstance(dimensions, int):
        dimensions = 0
    return (
        f"{provider.provider_name}:{provider.model_name}:"
        f"{getattr(provider, 'contract_version', 'v1')}:{dimensions}"
    )


def _filter_embedding_generation(
    candidates: list[RetrievedChunk], *, expected_identity: str
) -> tuple[list[RetrievedChunk], int, int]:
    filtered: list[RetrievedChunk] = []
    stale = 0
    legacy = 0
    for candidate in candidates:
        identity = (candidate.record.metadata_json or {}).get("embeddingIdentity")
        if not identity:
            legacy += 1
            filtered.append(candidate)
            continue
        if identity and identity != expected_identity:
            stale += 1
            continue
        filtered.append(candidate)
    return filtered, stale, legacy


def _intent_section_types(query: str) -> list[str]:
    tokens = set(_meaningful_tokens(query))
    normalized = " ".join(_tokens(query))

    if tokens.intersection({"nationality", "citizenship", "citizen", "national", "country"}):
        return ["fact.record", "participant.profile", "entity.profile", "transcript.window"]
    if _contains_any(normalized, ["quoc tich", "quốc tịch", "cong dan", "công dân", "nguoi nuoc nao", "người nước nào", "nuoc nao", "nước nào"]):
        return ["fact.record", "participant.profile", "entity.profile", "transcript.window"]

    if tokens.intersection({"participant", "participants", "attendee", "attendees", "speaker", "speakers", "people", "person", "role", "roles"}):
        return ["fact.participant_count", "fact.record", "participant.overview", "participant.profile", "entity.profile", "transcript.window"]
    if _contains_any(normalized, ["tham gia", "nguoi tham gia", "người tham gia", "bao nhieu nguoi", "bao nhiêu người", "co bao nhieu nguoi", "có bao nhiêu người", "ai tham gia", "vai tro", "vai trò", "nguoi noi", "người nói"]):
        return ["fact.participant_count", "fact.record", "participant.overview", "participant.profile", "entity.profile", "transcript.window"]

    if tokens.intersection({"quality", "confidence", "warning", "warnings", "coverage", "audio", "asr", "diarization", "transcription"}):
        return ["quality.overview", "quality.warning", "extraction.overview", "extraction.warning", "transcript.coverage", "fact.record", "participant.profile"]
    if _contains_any(normalized, ["chat luong", "chất lượng", "canh bao", "cảnh báo", "do tin cay", "độ tin cậy", "do phu", "độ phủ", "am thanh", "âm thanh", "nhan dang", "nhận dạng", "tach nguoi noi", "tách người nói"]):
        return ["quality.overview", "quality.warning", "extraction.overview", "extraction.warning", "transcript.coverage", "fact.record", "participant.profile"]

    if tokens.intersection({"provider", "model", "source", "asset", "file", "generated"}):
        return ["source.processing", "meeting.metadata", "quality.overview"]
    if _contains_any(normalized, ["mo hinh", "mô hình", "provider", "nguon", "nguồn", "tep", "tệp", "file nao", "file nào", "xu ly bang", "xử lý bằng", "phan tich bang", "phân tích bằng", "tao luc nao", "tạo lúc nào"]):
        return ["source.processing", "meeting.metadata", "quality.overview"]

    if tokens.intersection({"title", "duration", "started", "metadata"}):
        return ["meeting.metadata", "transcript.coverage", "source.processing"]
    if _contains_any(normalized, ["ten cuoc hop", "tên cuộc họp", "thoi luong", "thời lượng", "keo dai", "kéo dài", "bat dau", "bắt đầu"]):
        return ["meeting.metadata", "transcript.coverage", "source.processing"]

    if tokens.intersection({"empty", "missing", "unsupported", "unknown", "evidence"}):
        return ["extraction.warning", "extraction.overview", "quality.warning", "quality.overview", "transcript.coverage"]
    if _contains_any(normalized, ["khong co bang chung", "không có bằng chứng", "thieu bang chung", "thiếu bằng chứng", "khong xac dinh", "không xác định", "phan nao thieu", "phần nào thiếu", "muc nao thieu", "mục nào thiếu"]):
        return ["extraction.warning", "extraction.overview", "quality.warning", "quality.overview", "transcript.coverage"]

    if tokens.intersection({"metric", "metrics", "kpi", "number", "numbers", "target", "estimate", "threshold"}):
        return ["fact.record", "entity.profile", "summary.executive"]
    if _contains_any(normalized, ["so lieu", "số liệu", "chi so", "chỉ số", "kpi", "muc tieu", "mục tiêu", "uoc tinh", "ước tính", "nguong", "ngưỡng"]):
        return ["fact.record", "entity.profile", "summary.executive"]

    if tokens.intersection({"entity", "entities", "person", "company", "customer", "product", "project", "system"}):
        return ["entity.profile", "participant.profile", "fact.record"]
    if _contains_any(normalized, ["thuc the", "thực thể", "khach hang", "khách hàng", "san pham", "sản phẩm", "du an", "dự án", "he thong", "hệ thống"]):
        return ["entity.profile", "participant.profile", "fact.record"]

    if tokens.intersection({"glossary", "term", "terms", "acronym", "definition", "meaning"}):
        return ["entity.profile", "fact.record", "summary.executive"]
    if _contains_any(normalized, ["thuat ngu", "thuật ngữ", "viet tat", "viết tắt", "dinh nghia", "định nghĩa", "nghia la gi", "nghĩa là gì"]):
        return ["entity.profile", "fact.record", "summary.executive"]

    if tokens.intersection({"summary", "summarize", "overview", "topic", "topics", "main", "point", "points"}):
        return ["summary.executive", "summary.topic", "topic.summary", "summary.timeline"]
    if _contains_any(normalized, ["tom tat", "tóm tắt", "tong ket", "tổng kết", "y chinh", "ý chính", "noi dung", "nội dung", "ban ve", "bàn về", "van de", "vấn đề", "chu de", "chủ đề"]):
        return ["summary.executive", "summary.topic", "topic.summary", "summary.timeline"]

    if tokens.intersection({"reason", "reasons", "cause", "causes", "because", "why"}):
        return ["event.timeline", "relationship.edge", "fact.record", "risk.record", "summary.executive"]
    if _contains_any(normalized, ["tai sao", "tại sao", "vi sao", "vì sao", "ly do", "lý do", "nguyen nhan", "nguyên nhân", "do dau", "do đâu"]):
        return ["event.timeline", "relationship.edge", "fact.record", "risk.record", "summary.executive"]

    if tokens.intersection({"return", "returns", "refund", "exchange", "process", "policy", "procedure"}):
        return ["event.timeline", "action.item", "decision.record", "risk.record", "fact.record", "topic.summary"]
    if _contains_any(normalized, ["doi tra", "đổi trả", "tra hang", "trả hàng", "hoan tien", "hoàn tiền", "nhu nao", "như nào", "the nao", "thế nào", "cach", "cách", "quy trinh", "quy trình"]):
        return ["event.timeline", "action.item", "decision.record", "risk.record", "fact.record", "topic.summary"]

    if tokens.intersection({"action", "actions", "task", "tasks", "todo", "followup", "followups", "owner", "deadline"}):
        return ["action.item", "relationship.edge", "fact.record", "question.record"]
    if _contains_any(normalized, ["viec can lam", "việc cần làm", "can lam", "cần làm", "nhiem vu", "nhiệm vụ", "hanh dong", "hành động", "follow up", "theo doi", "theo dõi"]):
        return ["action.item", "relationship.edge", "fact.record", "question.record"]

    if tokens.intersection({"risk", "risks", "blocker", "blockers"}):
        return ["risk.record", "relationship.edge", "question.record", "event.timeline"]
    if _contains_any(normalized, ["rui ro", "rủi ro", "van de can luu y", "vấn đề cần lưu ý", "can luu y", "cần lưu ý", "tro ngai", "trở ngại"]):
        return ["risk.record", "relationship.edge", "question.record", "event.timeline"]

    if tokens.intersection({"decision", "decisions", "decide", "outcome", "outcomes"}):
        return ["decision.record", "event.timeline", "relationship.edge", "fact.record"]
    if _contains_any(normalized, ["quyet dinh", "quyết định", "ket qua", "kết quả", "thong nhat", "thống nhất"]):
        return ["decision.record", "event.timeline", "relationship.edge", "fact.record"]

    if tokens.intersection({"timeline", "deadline", "date", "dates", "time"}):
        return ["event.timeline", "fact.record", "action.item", "question.record", "summary.timeline"]
    if _contains_any(normalized, ["moc thoi gian", "mốc thời gian", "thoi han", "thời hạn", "deadline", "khi nao", "khi nào"]):
        return ["event.timeline", "fact.record", "action.item", "question.record", "summary.timeline"]

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


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


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
