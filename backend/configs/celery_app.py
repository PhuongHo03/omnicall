from celery import Celery

from backend.configs.settings import get_settings

settings = get_settings()

celery_app = Celery("omnicall", broker=settings.rabbitmq_url)
celery_app.conf.task_default_queue = "meeting-processing"
celery_app.conf.imports = ("backend.tasks.processing_tasks",)
celery_app.conf.worker_enable_remote_control = False
