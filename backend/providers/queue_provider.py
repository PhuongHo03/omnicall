from backend.configs.celery_app import celery_app


class ProcessingQueueProvider:
    task_name = "omnicall.processing.process_meeting"

    def enqueue_meeting_processing(self, *, job_id: str, meeting_id: str) -> None:
        celery_app.send_task(
            self.task_name,
            task_id=job_id,
            kwargs={"job_id": job_id, "meeting_id": meeting_id},
            queue="meeting-processing",
        )

    def revoke_meeting_processing(self, *, job_ids: list[str]) -> dict:
        requested = [job_id for job_id in job_ids if job_id]
        if not requested:
            return {"requested": 0, "revoked": 0, "status": "skipped"}
        try:
            celery_app.control.revoke(requested, terminate=False)
        except Exception as exc:
            return {
                "requested": len(requested),
                "revoked": 0,
                "status": "failed",
                "error": exc.__class__.__name__,
            }
        return {"requested": len(requested), "revoked": len(requested), "status": "requested"}


def get_processing_queue_provider() -> ProcessingQueueProvider:
    return ProcessingQueueProvider()
