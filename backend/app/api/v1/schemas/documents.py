"""Response models for documents, pages and evidence spans (B1)."""

from datetime import date, datetime

from pydantic import BaseModel


class DocumentSummary(BaseModel):
    id: int
    filename: str
    doc_type: str | None
    well_id: int | None
    well_name: str | None
    raw_well_name: str | None
    report_date: date | None
    page_count: int | None
    ingest_status: str
    error: str | None
    synthetic: bool
    size_bytes: int
    created_at: datetime
    processed_at: datetime | None


class DocumentList(BaseModel):
    items: list[DocumentSummary]
    total: int
    status_counts: dict[str, int]


class PageSummary(BaseModel):
    page_no: int
    ocr_used: bool
    ocr_mean_conf: float | None
    span_count: int


class DocumentDetail(DocumentSummary):
    sha256: str
    content_type: str
    uploaded_by: str | None
    pages: list[PageSummary]


class SpanOut(BaseModel):
    id: int
    line_no: int
    text: str
    bbox: list[float]
    conf: float | None


class PageOut(BaseModel):
    document_id: int
    page_no: int
    width_px: int
    height_px: int
    image_url: str
    ocr_used: bool
    ocr_mean_conf: float | None
    spans: list[SpanOut]


class UploadResult(BaseModel):
    document_id: int
    filename: str
    sha256: str
    status: str
    duplicate: bool
