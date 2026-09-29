"""Celery tasks for search indexing (queue: extract).

Contract stub: the task name, queue and argument are final; the search engineer replaces
the body with chunk embedding (``chunk.embedding`` / ``embedded_with``) and lesson-card
generation, recording progress in ``document.index_status`` / ``indexed_at``.
"""

import logging

from app.workers.celery_app import celery_app

log = logging.getLogger("smriti.search")


@celery_app.task(name="search.index_document", queue="extract")
def index_document_task(document_id: int) -> dict[str, object]:
    """Embed one document's chunks for dense retrieval (the tsvector is a generated column)."""
    log.info("search.index_document(%s): not implemented yet (phase B2)", document_id)
    return {"document_id": document_id, "status": "not_implemented"}
