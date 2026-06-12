from backend.configs.celery_app import celery_app
from backend.configs.database import SessionLocal
from backend.providers.analysis_provider import get_analysis_provider
from backend.providers.lock_provider import get_redis_lock_provider
from backend.providers.transcription_provider import get_transcription_provider
from backend.services.processing_pipeline_service import ProcessingPipelineService


@celery_app.task(name="omnicall.processing.process_meeting")
def process_meeting(job_id: str, meeting_id: str) -> dict[str, str]:
    with SessionLocal() as session:
        service = ProcessingPipelineService(
            session=session,
            lock_provider=get_redis_lock_provider(),
            transcription_provider=get_transcription_provider(),
            analysis_provider=get_analysis_provider(),
        )
        return service.process_meeting(job_id=job_id, meeting_id=meeting_id)
