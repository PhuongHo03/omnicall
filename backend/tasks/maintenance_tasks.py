from backend.configs.celery_app import celery_app
from backend.configs.database import SessionLocal
from backend.services.processing_reconciliation_service import ProcessingReconciliationService


@celery_app.task(
    name="omnicall.processing.reconcile_pending_jobs",
    acks_late=True,
    reject_on_worker_lost=True,
)
def reconcile_pending_processing_jobs() -> dict[str, int | str]:
    with SessionLocal() as session:
        return ProcessingReconciliationService(session=session).reconcile()
