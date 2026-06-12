from backend.configs.celery_app import celery_app


class ProcessingQueueProvider:
    task_name = "omnicall.processing.process_meeting"

    def enqueue_meeting_processing(self, *, job_id: str, meeting_id: str) -> None:
        celery_app.send_task(
            self.task_name,
            kwargs={"job_id": job_id, "meeting_id": meeting_id},
            queue="meeting-processing",
        )


def get_processing_queue_provider() -> ProcessingQueueProvider:
    return ProcessingQueueProvider()
