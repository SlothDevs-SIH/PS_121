"""Documents: upload, status, page evidence (S1, B1)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, UploadFile, status
from sqlalchemy import Select, distinct, func, select
from sqlalchemy.orm import Session

from app.api.v1.schemas.documents import (
    DocumentDetail,
    DocumentList,
    DocumentSummary,
    PageOut,
    PageSummary,
    SpanOut,
    UploadResult,
)
from app.core.audit import audit
from app.core.auth import CurrentUser, get_current_user, require
from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError
from app.db.models import Document, Event, EventEvidence, Page, TextSpan, Well
from app.db.session import get_session
from app.db.vocab import StageStatus
from app.ingest.service import store_upload
from app.storage.s3 import get_s3_client

router = APIRouter(tags=["documents"])
log = logging.getLogger("smriti.api.documents")
DbSession = Annotated[Session, Depends(get_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]
MAX_FILES_PER_REQUEST = 50


class TooManyFilesError(AppError):
    status_code = 413
    code = "too_many_files"


def event_counts_stmt(document_ids: list[int]) -> Select[tuple[int, int]]:
    """Active events citing each document (an event with several evidence spans in one
    document counts once)."""
    return (
        select(EventEvidence.document_id, func.count(distinct(EventEvidence.event_id)))
        .join(Event, Event.id == EventEvidence.event_id)
        .where(EventEvidence.document_id.in_(document_ids), Event.status == "active")
        .group_by(EventEvidence.document_id)
    )


def _event_counts(session: Session, document_ids: list[int]) -> dict[int, int]:
    if not document_ids:
        return {}
    return {int(d): int(n) for d, n in session.execute(event_counts_stmt(document_ids)).all()}


def _summary(doc: Document, well_name: str | None, event_count: int = 0) -> DocumentSummary:
    return DocumentSummary(
        id=doc.id,
        filename=doc.filename,
        doc_type=doc.doc_type,
        well_id=doc.well_id,
        well_name=well_name,
        raw_well_name=doc.raw_well_name,
        report_date=doc.report_date,
        page_count=doc.page_count,
        ingest_status=doc.ingest_status,
        error=doc.error,
        synthetic=doc.synthetic,
        size_bytes=doc.size_bytes,
        created_at=doc.created_at,
        processed_at=doc.processed_at,
        extract_status=doc.extract_status,  # CHECK-constrained to the StageStatus values
        index_status=doc.index_status,
        extract_error=doc.extract_error,
        event_count=event_count,
    )


def _get_doc(session: Session, document_id: int) -> Document:
    doc = session.get(Document, document_id)
    if doc is None:
        raise NotFoundError(f"Document {document_id} not found.", {"document_id": document_id})
    return doc


def _enqueue(document_ids: list[int]) -> None:
    from app.ingest.tasks import process_document_task

    for doc_id in document_ids:
        try:
            process_document_task.delay(doc_id)
        except Exception:  # broker down: rows stay 'queued' and can be re-queued later
            log.exception("could not enqueue document %s", doc_id)


@router.post(
    "/documents",
    dependencies=[Depends(require("ingest"))],
    summary="Upload report files and start ingestion",
    response_model=list[UploadResult],
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_documents(files: list[UploadFile], session: DbSession, user: User) -> list[UploadResult]:
    if len(files) > MAX_FILES_PER_REQUEST:
        raise TooManyFilesError(
            f"At most {MAX_FILES_PER_REQUEST} files per request.", {"max": MAX_FILES_PER_REQUEST}
        )
    results: list[UploadResult] = []
    new_ids: list[int] = []
    for f in files:
        stored = store_upload(session, f.filename or "upload", f.file.read(), user.user_id)
        doc = stored.document
        results.append(
            UploadResult(
                document_id=doc.id,
                filename=doc.filename,
                sha256=doc.sha256,
                status=doc.ingest_status,
                duplicate=stored.duplicate,
            )
        )
        if not stored.duplicate:
            new_ids.append(doc.id)
    audit(session, user, "document_upload", "document", None, files=len(files))
    session.commit()  # the worker must see the rows before it picks up the tasks
    _enqueue(new_ids)
    return results


@router.get("/documents", summary="List documents", response_model=DocumentList)
def list_documents(
    session: DbSession,
    well_id: int | None = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
    doc_type: str | None = None,
    extract_status: StageStatus | None = None,
    index_status: StageStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentList:
    stmt = select(Document, Well.canonical_name).outerjoin(Well, Well.id == Document.well_id)
    if well_id is not None:
        stmt = stmt.where(Document.well_id == well_id)
    if status_:
        stmt = stmt.where(Document.ingest_status == status_)
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    if extract_status:
        stmt = stmt.where(Document.extract_status == extract_status)
    if index_status:
        stmt = stmt.where(Document.index_status == index_status)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = session.execute(stmt.order_by(Document.id.desc()).limit(limit).offset(offset)).all()
    counts: dict[str, int] = {
        str(k): int(v)
        for k, v in session.execute(
            select(Document.ingest_status, func.count()).group_by(Document.ingest_status)
        ).all()
    }
    events = _event_counts(session, [d.id for d, _ in rows])
    return DocumentList(
        items=[_summary(d, n, events.get(d.id, 0)) for d, n in rows],
        total=int(total),
        status_counts=counts,
    )


@router.get(
    "/documents/{document_id}",
    summary="Document metadata and status",
    response_model=DocumentDetail,
)
def get_document(document_id: int, session: DbSession, user: User) -> DocumentDetail:
    doc = _get_doc(session, document_id)
    audit(session, user, "document_view", "document", doc.id)
    session.commit()
    well_name = session.get(Well, doc.well_id).canonical_name if doc.well_id else None  # type: ignore[union-attr]
    span_counts: dict[int, int] = dict(
        session.execute(  # type: ignore[arg-type]
            select(Page.page_no, func.count(TextSpan.id))
            .join(TextSpan, TextSpan.page_id == Page.id, isouter=True)
            .where(Page.document_id == doc.id)
            .group_by(Page.page_no)
        ).all()
    )
    return DocumentDetail(
        **_summary(doc, well_name, _event_counts(session, [doc.id]).get(doc.id, 0)).model_dump(),
        sha256=doc.sha256,
        content_type=doc.content_type,
        uploaded_by=doc.uploaded_by,
        pages=[
            PageSummary(
                page_no=p.page_no,
                ocr_used=p.ocr_used,
                ocr_mean_conf=p.ocr_mean_conf,
                span_count=int(span_counts.get(p.page_no, 0)),
            )
            for p in doc.pages
        ],
    )


def _get_page(session: Session, document_id: int, page_no: int) -> Page:
    page = session.scalar(
        select(Page).where(Page.document_id == document_id, Page.page_no == page_no)
    )
    if page is None:
        raise NotFoundError(
            f"Page {page_no} of document {document_id} not found.",
            {"document_id": document_id, "page_no": page_no},
        )
    return page


@router.get(
    "/documents/{document_id}/pages/{page_no}",
    summary="Page image and text spans for evidence highlighting",
    response_model=PageOut,
)
def get_page(document_id: int, page_no: int, session: DbSession) -> PageOut:
    page = _get_page(session, document_id, page_no)
    return PageOut(
        document_id=document_id,
        page_no=page.page_no,
        width_px=page.width_px,
        height_px=page.height_px,
        image_url=f"/api/v1/documents/{document_id}/pages/{page_no}/image",
        ocr_used=page.ocr_used,
        ocr_mean_conf=page.ocr_mean_conf,
        spans=[
            SpanOut(id=s.id, line_no=s.line_no, text=s.text, bbox=s.bbox, conf=s.conf)
            for s in page.spans
        ],
    )


@router.get(
    "/documents/{document_id}/pages/{page_no}/image",
    summary="Rendered page image (PNG)",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
def get_page_image(document_id: int, page_no: int, session: DbSession) -> Response:
    page = _get_page(session, document_id, page_no)
    body = (
        get_s3_client()
        .get_object(Bucket=get_settings().s3_bucket_pages, Key=page.image_key)["Body"]
        .read()
    )
    return Response(
        content=body, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"}
    )


@router.get(
    "/documents/{document_id}/file",
    summary="Original uploaded file",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
def get_file(document_id: int, session: DbSession, user: User) -> Response:
    doc = _get_doc(session, document_id)
    audit(session, user, "document_download", "document", doc.id)
    session.commit()
    body = (
        get_s3_client()
        .get_object(Bucket=get_settings().s3_bucket_raw, Key=doc.object_key)["Body"]
        .read()
    )
    return Response(
        content=body,
        media_type=doc.content_type,
        headers={"Content-Disposition": f'inline; filename="{doc.filename}"'},
    )


@router.post(
    "/documents/{document_id}/reprocess",
    dependencies=[Depends(require("ingest"))],
    summary="Re-run ingestion for a document",
    response_model=DocumentSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
def reprocess(document_id: int, session: DbSession, user: User) -> DocumentSummary:
    doc = _get_doc(session, document_id)
    doc.ingest_status, doc.error = "queued", None
    audit(session, user, "document_reprocess", "document", doc.id)
    session.commit()
    _enqueue([doc.id])
    return _summary(doc, None)
