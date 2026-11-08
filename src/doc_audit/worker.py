from celery import Celery
from celery.signals import setup_logging

from doc_audit.config import settings
from doc_audit.structured_logging import configure_json_logging

celery_app = Celery(
    "doc_audit",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["doc_audit.tasks"],
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "purge-expired-documents-daily": {
            "task": "doc_audit.purge_expired_documents",
            "schedule": 60 * 60 * 24,
        }
    },
)


@setup_logging.connect
def configure_worker_logging(**_kwargs: object) -> None:
    configure_json_logging()
