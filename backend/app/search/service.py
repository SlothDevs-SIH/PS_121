"""S5 search indexing: chunk embeddings and lessons-learned cards.

Runs after extraction (the extract task enqueues it). The full-text leg needs no work
here: ``chunk.tsv`` is a generated column, maintained by PostgreSQL.
"""

import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.db.models import Chunk, Document, Event, EventEvidence, Formation
from app.search import lessons
from app.search.embed import get_embedder

log = logging.getLogger("smriti.search")

BATCH = 32


def index_document(session: Session, document_id: int) -> dict[str, Any]:
    doc = session.get(Document, document_id)
    if doc is None:
        raise ValueError(f"document {document_id} not found")
    if doc.ingest_status not in ("processed", "needs_review"):
        doc.index_status = "skipped"
        doc.indexed_at = datetime.now(tz=UTC)
        return {"document_id": doc.id, "status": "skipped"}
    doc.index_status = "running"
    session.flush()

    embedder = get_embedder()
    chunks = list(
        session.execute(
            select(Chunk.id, Chunk.text).where(Chunk.document_id == doc.id).order_by(Chunk.id)
        ).all()
    )
    for k in range(0, len(chunks), BATCH):
        batch = chunks[k : k + BATCH]
        vectors = embedder.embed([c.text for c in batch])
        for c, vec in zip(batch, vectors, strict=True):
            session.execute(
                update(Chunk)
                .where(Chunk.id == c.id)
                .values(embedding=vec, embedded_with=embedder.name)
            )

    event_ids = session.scalars(
        select(EventEvidence.event_id).where(EventEvidence.document_id == doc.id).distinct()
    ).all()
    cards = refresh_lesson_cards(session, event_ids)

    doc.index_status = "done"
    doc.indexed_at = datetime.now(tz=UTC)
    session.flush()
    result = {"document_id": doc.id, "status": "done", "chunks": len(chunks), "lessons": cards}
    log.info("indexed document %s: %s", doc.id, result)
    return result


def refresh_lesson_cards(session: Session, event_ids: Iterable[int]) -> int:
    """(Re)write the lesson card of each event from its current fields."""
    ids = list(event_ids)
    if not ids:
        return 0
    names = dict(session.execute(select(Formation.id, Formation.name)).tuples().all())
    events = session.scalars(
        select(Event).where(Event.id.in_(ids)).options(selectinload(Event.mitigations))
    ).all()
    for ev in events:
        ev.lesson_card = lessons.build(ev, names.get(ev.formation_id) if ev.formation_id else None)
    session.flush()
    return len(events)


def mark_failed(session: Session, document_id: int, message: str) -> None:
    doc = session.get(Document, document_id)
    if doc is not None:
        doc.index_status = "failed"
        doc.extract_error = f"indexing: {message}"[:1000]
