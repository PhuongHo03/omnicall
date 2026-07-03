from celery import Celery
from kombu import Exchange, Queue

from backend.configs.settings import get_settings

settings = get_settings()

celery_app = Celery("omnicall", broker=settings.rabbitmq_url)
celery_app.conf.task_default_queue = "meeting-processing"
celery_app.conf.task_queues = (
    Queue(
        "meeting-processing",
        exchange=Exchange("meeting-processing", type="direct", durable=True),
        routing_key="meeting-processing",
        durable=True,
    ),
    Queue(
        "processing-maintenance",
        exchange=Exchange("processing-maintenance", type="direct", durable=True),
        routing_key="processing-maintenance",
        durable=True,
    ),
    Queue(
        "chat-processing",
        exchange=Exchange("chat-processing", type="direct", durable=True),
        routing_key="chat-processing",
        durable=True,
    ),
)
celery_app.conf.task_routes = {
    "omnicall.processing.process_meeting": {
        "queue": "meeting-processing",
        "routing_key": "meeting-processing",
    },
    "omnicall.processing.reconcile_pending_meetings": {
        "queue": "processing-maintenance",
        "routing_key": "processing-maintenance",
    },
    "omnicall.chat.generate_answer": {
        "queue": "chat-processing",
        "routing_key": "chat-processing",
    },
}
celery_app.conf.task_default_delivery_mode = "persistent"
celery_app.conf.worker_prefetch_multiplier = 1
celery_app.conf.imports = (
    "backend.tasks.processing_tasks",
    "backend.tasks.maintenance_tasks",
    "backend.tasks.chat_tasks",
)
celery_app.conf.worker_enable_remote_control = True
celery_app.conf.beat_schedule = {
    "reconcile-stale-queued-meetings": {
        "task": "omnicall.processing.reconcile_pending_meetings",
        "schedule": settings.processing_reconciliation_interval_seconds,
        "options": {
            "queue": "processing-maintenance",
            "routing_key": "processing-maintenance",
            "expires": max(settings.processing_reconciliation_interval_seconds * 2, 60),
        },
    },
}
