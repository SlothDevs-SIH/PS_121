"""Celery tasks for search indexing (queue: extract).

Runs after extraction: embeds the document's chunks for the dense leg (``chunk.embedding``
/ ``embedded_with``) and rewrites the lesson cards of the events it cites, recording
progress in ``document.index_status`` / ``indexed_at``.
"""

import logging

from app.db.session import session_scope
from app.ingest.tasks import TRANSIENT
from app.search.service import index_document, mark_failed
from app.workers.celery_app import celery_app

log = logging.getLogger("smriti.search")


@celery_app.task(
    name="search.index_document",
    queue="extract",
    autoretry_for=(*TRANSIENT, OSError),  # OSError: the embedding server was unreachable
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def index_document_task(document_id: int) -> dict[str, object]:
    """Embed one document's chunks and refresh its events' lesson cards."""
    try:
        with session_scope() as session:
            return index_document(session, document_id)
    except (*TRANSIENT, OSError):
        raise
    except Exception as exc:
        log.exception("indexing failed for document %s", document_id)
        with session_scope() as session:
            mark_failed(session, document_id, f"{type(exc).__name__}: {exc}")
        return {"document_id": document_id, "status": "failed"}
