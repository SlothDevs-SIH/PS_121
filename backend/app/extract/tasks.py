"""Celery tasks for schema extraction (queue: extract).

Runs after ingestion (the ingest task enqueues it) and, when done, enqueues search indexing
for the same document. Progress is recorded in ``document.extract_status`` /
``extract_error`` / ``extracted_at``.
"""

import logging

from app.db.session import session_scope
from app.extract.service import extract_document, mark_failed
from app.ingest.tasks import TRANSIENT
from app.workers.celery_app import celery_app

log = logging.getLogger("smriti.extract")


@celery_app.task(
    name="extract.process_document",
    queue="extract",
    autoretry_for=TRANSIENT,
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def process_document_task(document_id: int, index: bool = True) -> dict[str, object]:
    """Extract events, mitigations, casing, cement, mud and DDR lines from one document."""
    try:
        with session_scope() as session:
            result = extract_document(session, document_id)
    except TRANSIENT:
        raise
    except Exception as exc:  # permanent failure: record it on the row
        log.exception("extraction failed for document %s", document_id)
        with session_scope() as session:
            mark_failed(session, document_id, f"{type(exc).__name__}: {exc}")
        return {"document_id": document_id, "status": "failed"}
    if index:
        celery_app.send_task("search.index_document", args=[document_id])
    return result
