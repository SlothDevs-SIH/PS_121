"""S1 ingestion service: store uploads, then extract pages, spans, chunks and header facts."""

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core import metrics
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import Chunk, Document, Page, TextSpan
from app.ingest import classify
from app.ingest.chunking import chunk_lines
from app.ingest.pages import PageContent, extract_image, extract_pdf
from app.normalise.aliases import resolve_well
from app.storage.s3 import get_s3_client

log = logging.getLogger("smriti.ingest")

_MAGIC: tuple[tuple[bytes, str, str], ...] = (
    (b"%PDF", "application/pdf", ".pdf"),
    (b"\x89PNG", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"II*\x00", "image/tiff", ".tif"),
    (b"MM\x00*", "image/tiff", ".tif"),
)
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._\- ]+")


class UnsupportedFileError(AppError):
    status_code = 415
    code = "unsupported_file_type"


class FileTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"


@dataclass
class StoredUpload:
    document: Document
    duplicate: bool


def sniff(data: bytes) -> tuple[str, str]:
    for magic, ctype, ext in _MAGIC:
        if data.startswith(magic):
            return ctype, ext
    raise UnsupportedFileError(
        "Only PDF, PNG, JPEG and TIFF files are accepted.",
        {"accepted": ["pdf", "png", "jpeg", "tiff"]},
    )


def store_upload(
    session: Session, filename: str, data: bytes, uploaded_by: str | None
) -> StoredUpload:
    settings = get_settings()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise FileTooLargeError(
            f"File exceeds {settings.max_upload_mb} MB.", {"max_mb": settings.max_upload_mb}
        )
    ctype, ext = sniff(data)
    sha = hashlib.sha256(data).hexdigest()
    existing = session.scalar(select(Document).where(Document.sha256 == sha))
    if existing is not None:
        return StoredUpload(existing, duplicate=True)
    key = f"{sha[:2]}/{sha}{ext}"
    get_s3_client().put_object(Bucket=settings.s3_bucket_raw, Key=key, Body=data, ContentType=ctype)
    doc = Document(
        sha256=sha,
        object_key=key,
        filename=_SAFE_NAME.sub("_", filename)[:200] or f"upload{ext}",
        content_type=ctype,
        size_bytes=len(data),
        ingest_status="queued",
        uploaded_by=uploaded_by,
    )
    session.add(doc)
    session.flush()
    return StoredUpload(doc, duplicate=False)


def process_document(session: Session, document_id: int) -> Document:
    """Idempotent: re-running rebuilds this document's pages, spans and chunks."""
    settings = get_settings()
    doc = session.get(Document, document_id)
    if doc is None:
        raise ValueError(f"document {document_id} not found")
    doc.ingest_status, doc.error = "processing", None
    session.flush()

    s3 = get_s3_client()
    data = s3.get_object(Bucket=settings.s3_bucket_raw, Key=doc.object_key)["Body"].read()
    pages: list[PageContent] = (
        extract_pdf(data) if doc.content_type == "application/pdf" else extract_image(data)
    )

    session.execute(delete(Chunk).where(Chunk.document_id == doc.id))
    session.execute(delete(Page).where(Page.document_id == doc.id))
    session.flush()

    ordered: list[tuple[int, int, str]] = []
    for pc in pages:
        key = f"{doc.id}/{pc.page_no}.png"
        s3.put_object(
            Bucket=settings.s3_bucket_pages, Key=key, Body=pc.png, ContentType="image/png"
        )
        page = Page(
            document_id=doc.id,
            page_no=pc.page_no,
            width_px=pc.width_px,
            height_px=pc.height_px,
            image_key=key,
            ocr_used=pc.ocr_used,
            ocr_mean_conf=pc.mean_conf,
            text=pc.text,
        )
        page.spans = [
            TextSpan(line_no=i, text=ln.text, bbox=[round(v, 5) for v in ln.bbox], conf=ln.conf)
            for i, ln in enumerate(pc.lines)
        ]
        session.add(page)
        session.flush()
        ordered += [(pc.page_no, sp.id, sp.text) for sp in page.spans]

    first = pages[0].text if pages else ""
    all_text = "\n".join(p.text for p in pages)
    doc.page_count = len(pages)
    doc.doc_type = classify.classify(first)
    doc.synthetic = classify.is_synthetic(all_text)
    doc.report_date = classify.find_report_date(first, doc.doc_type)
    raw_name = classify.find_well_name(first)
    doc.raw_well_name = raw_name
    well = resolve_well(session, raw_name, doc.id) if raw_name else None
    doc.well_id = well.id if well else None

    for c in chunk_lines(ordered):
        session.add(
            Chunk(
                document_id=doc.id,
                well_id=doc.well_id,
                page_from=c.page_from,
                page_to=c.page_to,
                span_ids=c.span_ids,
                text=c.text,
            )
        )

    low_conf = [
        p.mean_conf
        for p in pages
        if p.ocr_used and p.mean_conf is not None and p.mean_conf < settings.ocr_needs_review_below
    ]
    reasons = []
    if doc.well_id is None:
        reasons.append(f"well not identified (read: {raw_name!r})")
    if low_conf:
        reasons.append(f"low OCR confidence on {len(low_conf)} page(s)")
    doc.ingest_status = "needs_review" if reasons else "processed"
    doc.error = "; ".join(reasons) or None
    doc.processed_at = datetime.now(tz=UTC)
    session.flush()
    metrics.record_pages([p.ocr_used for p in pages])
    metrics.DOCUMENTS_INGESTED.labels(status=doc.ingest_status).inc()
    log.info("processed document %s (%s pages, %s)", doc.id, doc.page_count, doc.ingest_status)
    return doc


def mark_failed(session: Session, document_id: int, message: str) -> None:
    doc = session.get(Document, document_id)
    if doc is not None:
        doc.ingest_status = "failed"
        doc.error = message[:1000]
    metrics.DOCUMENTS_INGESTED.labels(status="failed").inc()
