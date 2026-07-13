from backend.configs.celery_app import celery_app
from backend.configs.database import SessionLocal
from backend.providers.analysis import get_analysis_provider
from backend.providers.lock_provider import get_redis_lock_provider
from backend.providers.transcription_provider import get_transcription_provider
from backend.services.processing_pipeline_service import ProcessingPipelineService
from backend.services.processing.hierarchical_extraction_service import HierarchicalExtractionService
from backend.services.operational_log_service import get_operational_log_service
from backend.services.retrieval.index_service import RetrievalIndexService
from backend.providers.vector_provider import VectorProviderError, get_vector_provider


@celery_app.task(
    name="omnicall.processing.process_meeting",
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_meeting(meeting_id: str) -> dict[str, str]:
    with SessionLocal() as session:
        service = ProcessingPipelineService(
            session=session,
            lock_provider=get_redis_lock_provider(),
            transcription_provider=get_transcription_provider(),
            analysis_provider=get_analysis_provider(),
            operational_logs=get_operational_log_service(),
        )
        return service.process_meeting(meeting_id=meeting_id)


@celery_app.task(
    bind=True,
    name="omnicall.processing.repair_retrieval_index",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
)
def repair_retrieval_index(task, meeting_id: str) -> dict[str, str]:
    """Retry derived vector indexing without changing the authoritative result."""
    try:
        with SessionLocal() as session:
            service = RetrievalIndexService(session, vector_provider=get_vector_provider())
            chunks = service.rebuild_for_latest_result(meeting_id)
            vector_metadata = service.last_vector_metadata
            if vector_metadata.get("status") == "failed":
                raise VectorProviderError(vector_metadata.get("error", "Vector repair failed."))
            session.commit()
            return {"meeting_id": meeting_id, "status": "repaired", "chunk_count": str(len(chunks))}
    except Exception as exc:
        countdown = min(60, 2 ** (task.request.retries + 1))
        raise task.retry(exc=exc, countdown=countdown) from exc


@celery_app.task(
    bind=True,
    name="omnicall.processing.extract_transcript_window",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
)
def extract_transcript_window(task, meeting_id: str, generation: str, window_id: str) -> dict[str, str]:
    """Retryable unit of local extraction for a persisted transcript window."""
    try:
        with SessionLocal() as session:
            service = HierarchicalExtractionService(
                session=session,
                analysis_provider=get_analysis_provider(),
            )
            result = service.extract_window_for_task(
                meeting_id=meeting_id,
                generation=generation,
                window_id=window_id,
            )
            session.commit()
            return result
    except Exception as exc:
        countdown = min(120, 2 ** (task.request.retries + 1))
        raise task.retry(exc=exc, countdown=countdown) from exc
