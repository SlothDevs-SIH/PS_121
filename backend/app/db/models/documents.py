"""S1 tables: documents, pages, text spans (with bounding boxes) and search chunks.

B2 adds the per-document extraction/indexing stage columns (migration 0005) and the chunk
search columns (migration 0006).
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship

from app.db.base import Base
from app.db.types import Vector
from app.db.vocab import STAGE_STATUSES, in_list

EMBEDDING_DIM = 1024  # BGE-M3 dense size; the "hash" provider emits the same size


class Document(Base):
    __tablename__ = "document"
    __table_args__ = (
        CheckConstraint(in_list("extract_status", STAGE_STATUSES), name="extract_status"),
        CheckConstraint(in_list("index_status", STAGE_STATUSES), name="index_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    object_key: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    doc_type: Mapped[str | None] = mapped_column(String(20))
    well_id: Mapped[int | None] = mapped_column(
        ForeignKey("well.id", ondelete="SET NULL"), index=True
    )
    raw_well_name: Mapped[str | None] = mapped_column(Text)
    report_date: Mapped[date | None] = mapped_column(Date)
    page_count: Mapped[int | None] = mapped_column(Integer)
    ingest_status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_by: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # S2 extraction and S5 indexing run after ingestion: pending | running | done | failed | skipped
    extract_status: Mapped[str] = mapped_column(
        String(10), default="pending", server_default=text("'pending'"), index=True
    )
    index_status: Mapped[str] = mapped_column(
        String(10), default="pending", server_default=text("'pending'"), index=True
    )
    extract_error: Mapped[str | None] = mapped_column(Text)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    pages: Mapped[list["Page"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="Page.page_no"
    )


class Page(Base):
    __tablename__ = "page"
    __table_args__ = (UniqueConstraint("document_id", "page_no"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id", ondelete="CASCADE"))
    page_no: Mapped[int] = mapped_column(Integer)  # 1-based
    width_px: Mapped[int] = mapped_column(Integer)
    height_px: Mapped[int] = mapped_column(Integer)
    image_key: Mapped[str] = mapped_column(Text)
    ocr_used: Mapped[bool] = mapped_column(Boolean)
    ocr_mean_conf: Mapped[float | None] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text, default="")

    document: Mapped[Document] = relationship(back_populates="pages")
    spans: Mapped[list["TextSpan"]] = relationship(
        back_populates="page", cascade="all, delete-orphan", order_by="TextSpan.line_no"
    )


class TextSpan(Base):
    """One text line with its bounding box, normalised to the page: [x0, y0, x1, y1] in 0..1,
    origin top-left. This is what evidence links highlight."""

    __tablename__ = "text_span"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("page.id", ondelete="CASCADE"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    bbox: Mapped[list[float]] = mapped_column(ARRAY(Float))
    conf: Mapped[float | None] = mapped_column(Float)  # OCR confidence 0..100; null for text layer

    page: Mapped[Page] = relationship(back_populates="spans")


class Chunk(Base):
    __tablename__ = "chunk"
    __table_args__ = (
        Index("ix_chunk_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    well_id: Mapped[int | None] = mapped_column(
        ForeignKey("well.id", ondelete="SET NULL"), index=True
    )
    page_from: Mapped[int] = mapped_column(Integer)
    page_to: Mapped[int] = mapped_column(Integer)
    span_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger))
    text: Mapped[str] = mapped_column(Text)
    # Search columns (0006). Deferred: large, and only the search module reads them.
    embedding: Mapped[list[float] | None] = deferred(mapped_column(Vector(EMBEDDING_DIM)))
    tsv: Mapped[str | None] = deferred(
        mapped_column(TSVECTOR, Computed("to_tsvector('english', text)", persisted=True))
    )
    embedded_with: Mapped[str | None] = mapped_column(String(100))  # "<provider>:<model>"
