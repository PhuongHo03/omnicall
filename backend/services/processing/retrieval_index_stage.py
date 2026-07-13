import time
from dataclasses import dataclass
from typing import Callable

from backend.services.processing.observability import asset_log_context, elapsed_ms


@dataclass(frozen=True)
class RetrievalIndexStageResult:
    chunks: list[dict]
    metadata: dict
    duration_ms: int


class RetrievalIndexStage:
    def __init__(self, retrieval_index, settings, emit: Callable[..., None]) -> None:
        self.retrieval_index = retrieval_index
        self.settings = settings
        self.emit = emit

    def run(self, *, meeting, asset, result) -> RetrievalIndexStageResult:
        started = time.perf_counter()
        chunks = self.retrieval_index.rebuild_for_result(result)
        metadata = self.retrieval_index.last_index_metadata
        self.emit(
            level="info",
            flow="processing",
            stage="embedding",
            status="succeeded",
            message="Retrieval chunks and text embeddings generated.",
            workspace_id=meeting.owner_user_id,
            meeting_id=meeting.id,
            meeting_name=meeting.title,
            file=asset_log_context(asset),
            provider=metadata.get("embeddingProvider"),
            model=metadata.get("embeddingModel"),
            duration_ms=metadata.get("embeddingDurationMs"),
            details={
                "chunkCount": len(chunks),
                "embeddingIdentity": metadata.get("embeddingIdentity"),
                "batchSize": metadata.get("embeddingBatchSize"),
                "batchCount": metadata.get("embeddingBatchCount"),
            },
        )
        vector_metadata = metadata.get("vector", {})
        vector_failed = vector_metadata.get("status") == "failed"
        self.emit(
            level="error" if vector_failed else "info",
            flow="processing",
            stage="vector_upsert",
            status="failed" if vector_failed else "succeeded",
            message="Vector index update failed." if vector_failed else "Vector index updated.",
            workspace_id=meeting.owner_user_id,
            meeting_id=meeting.id,
            meeting_name=meeting.title,
            file=asset_log_context(asset),
            provider=metadata.get("vectorProvider"),
            model=self.settings.milvus_collection,
            duration_ms=metadata.get("vectorDurationMs"),
            details=vector_metadata,
            error_type="VectorProviderError" if vector_failed else None,
            error_message=vector_metadata.get("error") if vector_failed else None,
        )
        if vector_failed:
            from backend.tasks.processing_tasks import repair_retrieval_index

            repair_retrieval_index.delay(meeting.id)
        return RetrievalIndexStageResult(chunks=chunks, metadata=metadata, duration_ms=elapsed_ms(started))
