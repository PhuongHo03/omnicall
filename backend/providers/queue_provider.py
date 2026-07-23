from backend.configs.celery_app import celery_app


class ProcessingQueueProvider:
    task_name = "omnicall.processing.process_meeting"

    def enqueue_meeting_processing(self, *, meeting_id: str) -> None:
        celery_app.send_task(
            self.task_name,
            task_id=meeting_id,
            kwargs={"meeting_id": meeting_id},
            queue="meeting-processing",
        )

    def revoke_meeting_processing(self, *, meeting_ids: list[str]) -> dict:
        requested = [mid for mid in meeting_ids if mid]
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

    def enqueue_retrieval_repair(self, *, meeting_id: str, repair_token: str) -> None:
        celery_app.send_task(
            "omnicall.processing.repair_retrieval_index",
            kwargs={"meeting_id": meeting_id, "repair_token": repair_token},
            queue="processing-maintenance",
        )


def get_processing_queue_provider() -> ProcessingQueueProvider:
    return ProcessingQueueProvider()


class ChatQueueProvider:
    """Publish only durable identifiers; workers reload authoritative state."""

    def enqueue_turn(self, *, turn_id: str) -> None:
        celery_app.send_task(
            "omnicall.chat.generate_answer",
            kwargs={"turn_id": turn_id},
            queue="chat-processing",
        )

def get_chat_queue_provider() -> ChatQueueProvider:
    return ChatQueueProvider()
