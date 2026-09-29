"""Celery tasks for schema extraction (queue: extract).

Contract stub: the task name, queue and argument are final; the extract engineer replaces
the body with the rules + optional LLM pass, validation, confidence and review-queue writes,
recording progress in ``document.extract_status`` / ``extract_error`` / ``extracted_at``.
"""

import logging

from app.workers.celery_app import celery_app

log = logging.getLogger("smriti.extract")


@celery_app.task(name="extract.process_document", queue="extract")
def process_document_task(document_id: int) -> dict[str, object]:
    """Extract events, mitigations, casing, cement, mud and DDR lines from one document."""
    log.info("extract.process_document(%s): not implemented yet (phase B2)", document_id)
    return {"document_id": document_id, "status": "not_implemented"}
