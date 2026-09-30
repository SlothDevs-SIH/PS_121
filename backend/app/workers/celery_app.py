"""Celery application. Run: ``celery -A app.workers.celery_app worker -l INFO``.

Queues (docs/BACKEND_PLAN.md section 9):
- ``ingest``: ``ingest.process_document`` (OCR-heavy);
- ``extract``: ``extract.process_document`` and ``search.index_document`` (LLM / embedding);
- ``default``: ``system.ping`` and light housekeeping.

Metrics (B6): the worker's main process serves ``/metrics`` on ``SMRITI_WORKER_METRICS_PORT``;
the pool's child processes, which run the tasks, write theirs to files in
``PROMETHEUS_MULTIPROC_DIR`` that the main process adds up (prometheus_client multiprocess
mode). Only a ``celery worker`` (not the API, which just sends tasks) sets this up.
"""

import logging
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from celery import Celery, signals

from app.core.config import get_settings

log = logging.getLogger("smriti.worker")
settings = get_settings()

celery_app = Celery(
    "smriti",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.ingest.tasks", "app.extract.tasks", "app.search.tasks"],
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
    # Explicit routes so a producer that only knows the task name still hits the right queue.
    task_routes={
        "ingest.*": {"queue": "ingest"},
        "extract.*": {"queue": "extract"},
        "search.*": {"queue": "extract"},
    },
)


@celery_app.task(name="system.ping")
def ping() -> dict[str, str]:
    """Round-trip check used by `app.cli check --worker` and the integration tests."""
    return {"pong": datetime.now(tz=UTC).isoformat()}


def prepare_multiprocess_metrics() -> Path:
    """Put this process (and the children it forks) in prometheus_client multiprocess mode.

    Must run before prometheus_client is first imported: the mode is chosen at import time.
    Stale files from an earlier run of the worker are removed.
    """
    if "prometheus_client" in sys.modules:
        log.warning("prometheus_client already imported: pool metrics will not be aggregated")
    path = Path(
        os.environ.get("PROMETHEUS_MULTIPROC_DIR") or tempfile.mkdtemp(prefix="smriti-metrics-")
    )
    path.mkdir(parents=True, exist_ok=True)
    for stale in path.glob("*.db"):
        stale.unlink(missing_ok=True)
    os.environ["PROMETHEUS_MULTIPROC_DIR"] = str(path)
    return path


@signals.import_modules.connect
def _worker_starting(**_: object) -> None:
    # Sent by `celery worker` (also `beat`, `report`; not `inspect` or the API's task sends)
    # just before it imports the task modules, which define the metrics.
    if settings.metrics_enabled:
        prepare_multiprocess_metrics()


@signals.worker_ready.connect
def _worker_ready(**_: object) -> None:
    if settings.metrics_enabled:
        from app.core import metrics

        metrics.serve(settings.worker_metrics_port)


@signals.worker_process_shutdown.connect
def _pool_process_exit(pid: int | None = None, **_: object) -> None:
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
        from prometheus_client import multiprocess

        multiprocess.mark_process_dead(pid or os.getpid())  # type: ignore[no-untyped-call]
