"""B1: documents, pages, text spans (bbox evidence), chunks, well-alias candidates.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("doc_type", sa.String(length=20), nullable=True),
        sa.Column("well_id", sa.Integer(), nullable=True),
        sa.Column("raw_well_name", sa.Text(), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("ingest_status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("synthetic", sa.Boolean(), nullable=False),
        sa.Column("uploaded_by", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["well_id"], ["well.id"], name=op.f("fk_document_well_id_well"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document")),
        sa.UniqueConstraint("sha256", name=op.f("uq_document_sha256")),
    )
    op.create_index(op.f("ix_document_ingest_status"), "document", ["ingest_status"], unique=False)
    op.create_index(op.f("ix_document_well_id"), "document", ["well_id"], unique=False)
    op.create_table(
        "page",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("width_px", sa.Integer(), nullable=False),
        sa.Column("height_px", sa.Integer(), nullable=False),
        sa.Column("image_key", sa.Text(), nullable=False),
        sa.Column("ocr_used", sa.Boolean(), nullable=False),
        sa.Column("ocr_mean_conf", sa.Float(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_page_document_id_document"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_page")),
        sa.UniqueConstraint("document_id", "page_no", name=op.f("uq_page_document_id")),
    )
    op.create_table(
        "text_span",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("page_id", sa.BigInteger(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("bbox", postgresql.ARRAY(sa.Float()), nullable=False),
        sa.Column("conf", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["page_id"], ["page.id"], name=op.f("fk_text_span_page_id_page"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_text_span")),
    )
    op.create_index(op.f("ix_text_span_page_id"), "text_span", ["page_id"], unique=False)
    op.create_table(
        "chunk",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("well_id", sa.Integer(), nullable=True),
        sa.Column("page_from", sa.Integer(), nullable=False),
        sa.Column("page_to", sa.Integer(), nullable=False),
        sa.Column("span_ids", postgresql.ARRAY(sa.BigInteger()), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_chunk_document_id_document"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["well_id"], ["well.id"], name=op.f("fk_chunk_well_id_well"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunk")),
    )
    op.create_index(op.f("ix_chunk_document_id"), "chunk", ["document_id"], unique=False)
    op.create_index(op.f("ix_chunk_well_id"), "chunk", ["well_id"], unique=False)
    op.create_table(
        "alias_candidate",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("raw_name", sa.Text(), nullable=False),
        sa.Column("well_id", sa.Integer(), nullable=True),
        sa.Column("similarity", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_alias_candidate_document_id_document"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["well_id"],
            ["well.id"],
            name=op.f("fk_alias_candidate_well_id_well"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alias_candidate")),
    )


def downgrade() -> None:
    op.drop_table("alias_candidate")
    op.drop_table("chunk")
    op.drop_table("text_span")
    op.drop_table("page")
    op.drop_table("document")
