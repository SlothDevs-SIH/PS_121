"""Celery application. Run: ``celery -A app.workers.celery_app worker -l INFO``.

Queues (master plan S1/S2 batch work lands here from B1): ``ingest``, ``extract``, ``default``.
"""

from datetime import UTC, datetime

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "smriti",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.ingest.tasks"],
)
celery_app.conf.update(
    task_default_queue="default",
    task_acks_late=True,  # re-run a task if the worker dies mid-way
    worker_prefetch_multiplier=1,  # OCR/LLM tasks are long; don't hoard them
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600,
    timezone="UTC",
    broker_connection_retry_on_startup=True,
)


@celery_app.task(name="system.ping")
def ping() -> dict[str, str]:
    """Round-trip check used by `app.cli check --worker` and the integration tests."""
    return {"pong": datetime.now(tz=UTC).isoformat()}
