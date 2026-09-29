"""Evidence references for API responses: group cited spans by document page."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.schemas.common import EvidenceRef
from app.db.models import Document, EventEvidence


def _doc_names(session: Session, doc_ids: set[int]) -> dict[int, tuple[str, str | None]]:
    if not doc_ids:
        return {}
    rows = session.execute(
        select(Document.id, Document.filename, Document.doc_type).where(Document.id.in_(doc_ids))
    ).all()
    return {r.id: (r.filename, r.doc_type) for r in rows}


def event_evidence_refs(session: Session, event_ids: Iterable[int]) -> dict[int, list[EvidenceRef]]:
    """event id -> evidence refs, primary spans first, one ref per (document, page)."""
    ids = list(event_ids)
    if not ids:
        return {}
    rows = session.execute(
        select(EventEvidence)
        .where(EventEvidence.event_id.in_(ids))
        .order_by(EventEvidence.event_id, EventEvidence.document_id, EventEvidence.page_no)
    ).scalars()
    grouped: dict[int, dict[tuple[int, int], tuple[bool, list[int]]]] = {}
    for ev in rows:
        pages = grouped.setdefault(ev.event_id, {})
        primary, spans = pages.get((ev.document_id, ev.page_no), (False, []))
        spans.append(ev.span_id)
        pages[(ev.document_id, ev.page_no)] = (primary or ev.role == "primary", spans)
    names = _doc_names(session, {d for pages in grouped.values() for d, _ in pages})
    out: dict[int, list[EvidenceRef]] = {}
    for event_id, pages in grouped.items():
        refs = sorted(pages.items(), key=lambda kv: (not kv[1][0], kv[0]))
        out[event_id] = [
            EvidenceRef(
                document_id=doc_id,
                page_no=page_no,
                span_ids=sorted(spans),
                filename=names.get(doc_id, ("", None))[0] or None,
                doc_type=names.get(doc_id, ("", None))[1],
            )
            for (doc_id, page_no), (_, spans) in refs
        ]
    return out


def record_evidence(
    session: Session, rows: Iterable[tuple[int | None, int | None, list[int]]]
) -> list[list[EvidenceRef]]:
    """Evidence for EvidenceMixin rows given as (document_id, page_no, span_ids)."""
    items = list(rows)
    names = _doc_names(session, {d for d, _, _ in items if d is not None})
    return [
        []
        if doc_id is None or page_no is None
        else [
            EvidenceRef(
                document_id=doc_id,
                page_no=page_no,
                span_ids=list(spans or []),
                filename=names.get(doc_id, ("", None))[0] or None,
                doc_type=names.get(doc_id, ("", None))[1],
            )
        ]
        for doc_id, page_no, spans in items
    ]
