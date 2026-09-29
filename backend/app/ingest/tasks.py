"""Celery tasks for ingestion (queue: ingest)."""

import logging

from botocore.exceptions import BotoCoreError, EndpointConnectionError
from sqlalchemy.exc import OperationalError

from app.db.session import session_scope
from app.ingest.service import mark_failed, process_document
from app.workers.celery_app import celery_app

log = logging.getLogger("smriti.ingest")

TRANSIENT = (OperationalError, EndpointConnectionError, ConnectionError)


@celery_app.task(
    name="ingest.process_document",
    queue="ingest",
    autoretry_for=TRANSIENT,
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def process_document_task(document_id: int) -> dict[str, object]:
    try:
        with session_scope() as session:
            doc = process_document(session, document_id)
            result: dict[str, object] = {
                "document_id": doc.id,
                "status": doc.ingest_status,
                "pages": doc.page_count,
            }
    except TRANSIENT:
        raise
    except (BotoCoreError, Exception) as exc:  # permanent failure: record it on the row
        log.exception("ingestion failed for document %s", document_id)
        with session_scope() as session:
            mark_failed(session, document_id, f"{type(exc).__name__}: {exc}")
        return {"document_id": document_id, "status": "failed"}
    # Next stage by name, so ingestion doesn't import the extraction code.
    celery_app.send_task("extract.process_document", args=[document_id])
    return result
