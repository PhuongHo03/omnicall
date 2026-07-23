import hashlib
import json
import time

from sqlalchemy.orm import Session

from backend.configs.settings import Settings, get_settings
from backend.models.meeting_models import MeetingIntelligenceResult
from backend.providers.embedding_provider import TextEmbeddingProvider, get_embedding_provider
from backend.providers.vector_provider import VectorProvider, VectorProviderError, get_vector_provider
from backend.repositories.meeting_repository import MeetingIntelligenceResultRepository
from backend.repositories.retrieval_repository import MeetingChunkRepository
from backend.services.retrieval.chunk_builder import build_retrieval_chunks, elapsed_ms
from backend.services.simple_rag.contracts import RETRIEVAL_CONTRACT_VERSION



class RetrievalIndexService:
    def __init__(
        self,
        session: Session,
        embedding_provider: TextEmbeddingProvider | None = None,
        vector_provider: VectorProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
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
        generation = _index_generation(
            result_id=result.id,
            result_json=result.result_json,
            embedding_identity=_embedding_identity(self.embedding_provider, chunk_dicts),
        )
        for chunk in chunk_dicts:
            chunk.setdefault("metadata", {})["indexGeneration"] = generation
        embedding_duration_ms = elapsed_ms(embedding_started)
        records = self.chunks.replace_for_result(
            meeting_id=result.meeting_id,
            intelligence_result_id=result.id,
            chunks=chunk_dicts,
        )
        vector_started = time.perf_counter()
        self.last_vector_metadata = self._upsert_vectors(records)
        vector_duration_ms = elapsed_ms(vector_started)
        self.last_index_metadata = {
            "chunkCount": len(records),
            "embeddingProvider": self.embedding_provider.provider_name,
            "embeddingModel": self.embedding_provider.model_name,
            "embeddingDimensions": _provider_dimensions(self.embedding_provider, records),
            "embeddingContractVersion": getattr(self.embedding_provider, "contract_version", "v1"),
            "embeddingIdentity": _embedding_identity(self.embedding_provider, records),
            "embeddingBatchSize": getattr(self.embedding_provider, "batch_size", len(records)),
            "embeddingBatchCount": getattr(self.embedding_provider, "last_batch_count", 1),
            "embeddingInputCount": getattr(self.embedding_provider, "last_input_count", len(records)),
            "embeddingDurationMs": embedding_duration_ms,
            "vectorProvider": self.vector_provider.provider_name,
            "vectorDurationMs": vector_duration_ms,
            "vector": self.last_vector_metadata,
            "indexGeneration": generation,
            "retrievalContract": RETRIEVAL_CONTRACT_VERSION,
        }
        embedding_identity = _embedding_identity(self.embedding_provider, records)
        self.chunks.upsert_snapshot(
            meeting_id=result.meeting_id,
            intelligence_result_id=result.id,
            index_generation=generation,
            embedding_identity=embedding_identity,
            retrieval_contract=RETRIEVAL_CONTRACT_VERSION,
            chunk_count=len(records),
            error=(
                "vector_repair_pending"
                if self.last_vector_metadata.get("status") == "failed"
                else None
            ),
        )
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


def _provider_dimensions(provider, records: list) -> int | None:
    configured = getattr(provider, "expected_dimensions", None)
    if isinstance(configured, int):
        return configured
    for record in records:
        embedding = record.get("embedding") if isinstance(record, dict) else getattr(record, "embedding", None)
        if isinstance(embedding, list):
            return len(embedding)
    return None


def _embedding_identity(provider, records: list) -> str:
    dimensions = _provider_dimensions(provider, records) or 0
    return (
        f"{provider.provider_name}:{provider.model_name}:"
        f"{getattr(provider, 'contract_version', 'v1')}:{dimensions}"
    )


def _index_generation(*, result_id: str, result_json: dict, embedding_identity: str) -> str:
    digest = hashlib.sha256(
        json.dumps(result_json, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()[:24]
    return f"{digest}:{result_id}:{embedding_identity}"[:180]
