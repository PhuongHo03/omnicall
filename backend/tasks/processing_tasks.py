from backend.configs.celery_app import celery_app
from backend.configs.database import SessionLocal
from backend.providers.analysis_provider import get_analysis_provider
from backend.providers.lock_provider import get_redis_lock_provider
from backend.providers.transcription_provider import get_transcription_provider
from backend.services.processing_pipeline_service import ProcessingPipelineService
from backend.services.operational_log_service import get_operational_log_service


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
