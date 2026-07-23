from backend.configs.celery_app import celery_app
from backend.configs.database import SessionLocal
from backend.configs.settings import get_settings
from backend.providers.analysis import get_analysis_provider
from backend.providers.lock_provider import LockHeartbeat, ProcessingLockLostError, get_redis_lock_provider
from backend.providers.transcription_provider import get_transcription_provider
from backend.services.processing_pipeline_service import ProcessingPipelineService
from backend.services.processing.hierarchical_extraction_service import HierarchicalExtractionService
from backend.services.operational_log_service import get_operational_log_service
from backend.services.retrieval.index_service import RetrievalIndexService
from backend.providers.vector_provider import VectorProviderError, get_vector_provider
from backend.repositories.retrieval_repository import MeetingChunkRepository


@celery_app.task(
    bind=True,
    name="omnicall.processing.process_meeting",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
)
def process_meeting(task, meeting_id: str) -> dict[str, str]:
    try:
        with SessionLocal() as session:
            service = ProcessingPipelineService(
                session=session,
                lock_provider=get_redis_lock_provider(),
                transcription_provider=get_transcription_provider(),
                analysis_provider=get_analysis_provider(),
                operational_logs=get_operational_log_service(),
            )
            result = service.process_meeting(meeting_id=meeting_id)
    except Exception as exc:
        countdown = min(60, 2 ** (task.request.retries + 1))
        raise task.retry(exc=exc, countdown=countdown) from exc
    if result.get("status") == "lock_lost":
        countdown = min(60, 2 ** (task.request.retries + 1))
        raise task.retry(
            exc=ProcessingLockLostError("Meeting processing lock ownership was lost."),
            countdown=countdown,
        )
    return result


@celery_app.task(
    bind=True,
    name="omnicall.processing.repair_retrieval_index",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
)
def repair_retrieval_index(
    task,
    meeting_id: str,
    repair_token: str | None = None,
) -> dict[str, str]:
    """Retry derived vector indexing without changing the authoritative result."""
    if not repair_token:
        # Pre-claim broker messages can survive a rolling deployment. They are
        # ignored; the durable pending row will be claimed by reconciliation.
        return {"meeting_id": meeting_id, "status": "unclaimed", "chunk_count": "0"}

    settings = get_settings()
    repair_lease_seconds = max(
        60,
        int(settings.redis_processing_lock_ttl_seconds),
        int(settings.processing_reconciliation_stale_seconds) * 2,
    )
    lock_provider = get_redis_lock_provider()
    lock_key = f"lock:meeting-processing:{meeting_id}"
    lock_token = lock_provider.acquire(lock_key)
    if lock_token is None:
        raise task.retry(countdown=min(60, 2 ** (task.request.retries + 1)))
    heartbeat = LockHeartbeat(
        lock_provider,
        key=lock_key,
        token=lock_token,
        ttl_seconds=settings.redis_processing_lock_ttl_seconds,
    )
    try:
        heartbeat.start()
        with SessionLocal() as claim_session:
            claims = MeetingChunkRepository(claim_session)
            if not claims.mark_repair_started_if_owned(
                meeting_id=meeting_id,
                token=repair_token,
                lease_seconds=repair_lease_seconds,
            ):
                claim_session.rollback()
                return {"meeting_id": meeting_id, "status": "noop", "chunk_count": "0"}
            claim_session.commit()

        with SessionLocal() as session:
            claims = MeetingChunkRepository(session)
            if claims.lock_started_repair_if_owned(
                meeting_id=meeting_id,
                token=repair_token,
            ) is None:
                session.rollback()
                return {"meeting_id": meeting_id, "status": "noop", "chunk_count": "0"}
            service = RetrievalIndexService(session, vector_provider=get_vector_provider())
            result = service.results.get_latest_for_meeting(meeting_id)
            if result is None:
                claims.finish_repair_if_owned(
                    meeting_id=meeting_id,
                    token=repair_token,
                    error="retrieval_result_missing",
                )
                heartbeat.assert_owned(refresh=True)
                session.commit()
                return {"meeting_id": meeting_id, "status": "missing", "chunk_count": "0"}
            chunks = service.rebuild_for_result(result)
            vector_metadata = service.last_vector_metadata
            if vector_metadata.get("status") == "failed":
                raise VectorProviderError(vector_metadata.get("error", "Vector repair failed."))
            claims.finish_repair_if_owned(
                meeting_id=meeting_id,
                token=repair_token,
            )
            heartbeat.assert_owned(refresh=True)
            session.commit()
            return {"meeting_id": meeting_id, "status": "repaired", "chunk_count": str(len(chunks))}
    except Exception as exc:
        countdown = min(60, 2 ** (task.request.retries + 1))
        try:
            with SessionLocal() as retry_session:
                MeetingChunkRepository(retry_session).requeue_repair_if_owned(
                    meeting_id=meeting_id,
                    token=repair_token,
                    lease_seconds=max(repair_lease_seconds, countdown * 2),
                    error=f"vector_repair_retry:{type(exc).__name__}",
                )
                retry_session.commit()
        except Exception:
            # A database outage must not suppress Celery retry. The persisted
            # lease still lets reconciliation recover the claim later.
            pass
        raise task.retry(exc=exc, countdown=countdown) from exc
    finally:
        heartbeat.stop()
        try:
            lock_provider.release(lock_key, lock_token)
        except Exception:
            # Compare-and-expire renewal has stopped, so Redis will release the
            # token by TTL even when an explicit cleanup call is unavailable.
            pass


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
