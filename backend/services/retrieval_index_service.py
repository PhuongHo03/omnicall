import time

from sqlalchemy.orm import Session

from backend.models.meeting_models import MeetingIntelligenceResult
from backend.providers.embedding_provider import TextEmbeddingProvider, get_embedding_provider
from backend.providers.vector_provider import VectorProvider, VectorProviderError, get_vector_provider
from backend.repositories.meeting_repository import MeetingIntelligenceResultRepository
from backend.repositories.retrieval_repository import MeetingChunkRepository
from backend.services.retrieval_chunk_builder import build_retrieval_chunks, elapsed_ms



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


