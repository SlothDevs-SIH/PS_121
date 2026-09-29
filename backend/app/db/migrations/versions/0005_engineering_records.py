"""B2: engineering records - events (+ evidence, mitigations), casing, cement, mud, DDR time
log, review queue; document extraction/indexing stage columns; well.fluid_type.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import SchemaItem

from app.db.vocab import (
    CEMENT_RETURNS,
    EVENT_SOURCES,
    EVENT_STATUSES,
    EVENT_TYPES,
    EVIDENCE_ROLES,
    FLUID_TYPES,
    MITIGATION_OUTCOMES,
    REVIEW_KINDS,
    REVIEW_STATUSES,
    SEVERITIES,
    STAGE_STATUSES,
    in_list,
)

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONFIDENCE_RANGE = "confidence >= 0 AND confidence <= 1"


def _confidence(table: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(CONFIDENCE_RANGE, name=op.f(f"ck_{table}_confidence"))


def _evidence_columns(table: str) -> list[SchemaItem]:
    """document_id / page_no / span_ids / confidence / verified (app.db.models EvidenceMixin)."""
    return [
        sa.Column("document_id", sa.BigInteger(), nullable=True),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column(
            "span_ids",
            postgresql.ARRAY(sa.BigInteger()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f(f"fk_{table}_document_id_document"),
            ondelete="CASCADE",
        ),
        _confidence(table),
    ]


def upgrade() -> None:
    # ── Existing tables ──
    op.add_column("well", sa.Column("fluid_type", sa.String(length=10), nullable=True))
    op.create_check_constraint(
        op.f("ck_well_fluid_type"), "well", in_list("fluid_type", FLUID_TYPES)
    )
    for stage in ("extract_status", "index_status"):
        op.add_column(
            "document",
            sa.Column(
                stage, sa.String(length=10), server_default=sa.text("'pending'"), nullable=False
            ),
        )
        op.create_check_constraint(
            op.f(f"ck_document_{stage}"), "document", in_list(stage, STAGE_STATUSES)
        )
        op.create_index(op.f(f"ix_document_{stage}"), "document", [stage], unique=False)
    op.add_column("document", sa.Column("extract_error", sa.Text(), nullable=True))
    op.add_column("document", sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("document", sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True))

    # ── Events ──
    op.create_table(
        "event",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("well_id", sa.Integer(), nullable=False),
        sa.Column("wellbore_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("subtype", sa.String(length=40), nullable=True),
        sa.Column("severity", sa.String(length=10), nullable=True),
        sa.Column("t_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("t_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("md_m", sa.Float(), nullable=True),
        sa.Column("tvd_m", sa.Float(), nullable=True),
        sa.Column("tvdss_m", sa.Float(), nullable=True),
        sa.Column("formation_id", sa.Integer(), nullable=True),
        sa.Column("hole_size_in", sa.Float(), nullable=True),
        sa.Column("mw_sg", sa.Float(), nullable=True),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("cause_text", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("npt_hours", sa.Float(), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=True),
        sa.Column("lesson_card", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("verified_by", sa.String(length=100), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column(
            "status", sa.String(length=10), server_default=sa.text("'active'"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(in_list("event_type", EVENT_TYPES), name=op.f("ck_event_event_type")),
        sa.CheckConstraint(in_list("severity", SEVERITIES), name=op.f("ck_event_severity")),
        sa.CheckConstraint(in_list("source", EVENT_SOURCES), name=op.f("ck_event_source")),
        sa.CheckConstraint(in_list("status", EVENT_STATUSES), name=op.f("ck_event_status")),
        _confidence("event"),
        sa.ForeignKeyConstraint(
            ["well_id"], ["well.id"], name=op.f("fk_event_well_id_well"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["wellbore_id"],
            ["wellbore.id"],
            name=op.f("fk_event_wellbore_id_wellbore"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["formation_id"],
            ["formation.id"],
            name=op.f("fk_event_formation_id_formation"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event")),
    )
    op.create_index("ix_event_well_id_md_m", "event", ["well_id", "md_m"], unique=False)
    op.create_index(op.f("ix_event_wellbore_id"), "event", ["wellbore_id"], unique=False)
    op.create_index(op.f("ix_event_event_type"), "event", ["event_type"], unique=False)
    op.create_index(op.f("ix_event_event_date"), "event", ["event_date"], unique=False)
    op.create_index(op.f("ix_event_formation_id"), "event", ["formation_id"], unique=False)

    op.create_table(
        "event_evidence",
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("span_id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column(
            "role", sa.String(length=10), server_default=sa.text("'primary'"), nullable=False
        ),
        sa.CheckConstraint(in_list("role", EVIDENCE_ROLES), name=op.f("ck_event_evidence_role")),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["event.id"],
            name=op.f("fk_event_evidence_event_id_event"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["span_id"],
            ["text_span.id"],
            name=op.f("fk_event_evidence_span_id_text_span"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_event_evidence_document_id_document"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("event_id", "span_id", name=op.f("pk_event_evidence")),
    )
    op.create_index(
        op.f("ix_event_evidence_document_id"), "event_evidence", ["document_id"], unique=False
    )

    op.create_table(
        "mitigation",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("action_code", sa.String(length=40), nullable=False),
        sa.Column("action_text", sa.Text(), nullable=True),
        sa.Column("t_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "outcome", sa.String(length=10), server_default=sa.text("'unknown'"), nullable=False
        ),
        sa.Column("npt_hours_after", sa.Float(), nullable=True),
        sa.Column("volume_lost_m3", sa.Float(), nullable=True),
        sa.Column("recurrence", sa.Boolean(), nullable=True),
        *_evidence_columns("mitigation"),
        sa.CheckConstraint(
            in_list("outcome", MITIGATION_OUTCOMES), name=op.f("ck_mitigation_outcome")
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["event.id"],
            name=op.f("fk_mitigation_event_id_event"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mitigation")),
        sa.UniqueConstraint("event_id", "seq", name=op.f("uq_mitigation_event_id")),
    )
    op.create_index(op.f("ix_mitigation_action_code"), "mitigation", ["action_code"], unique=False)
    op.create_index(op.f("ix_mitigation_document_id"), "mitigation", ["document_id"], unique=False)

    # ── Casing, cement, mud ──
    op.create_table(
        "casing_string",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("wellbore_id", sa.Integer(), nullable=False),
        sa.Column("od_in", sa.Float(), nullable=True),
        sa.Column("hole_size_in", sa.Float(), nullable=True),
        sa.Column("shoe_md_m", sa.Float(), nullable=True),
        sa.Column("shoe_tvd_m", sa.Float(), nullable=True),
        sa.Column("shoe_tvdss_m", sa.Float(), nullable=True),
        sa.Column("planned_shoe_md_m", sa.Float(), nullable=True),
        sa.Column("grade", sa.String(length=20), nullable=True),
        sa.Column("weight_ppf", sa.Float(), nullable=True),
        *_evidence_columns("casing_string"),
        sa.ForeignKeyConstraint(
            ["wellbore_id"],
            ["wellbore.id"],
            name=op.f("fk_casing_string_wellbore_id_wellbore"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_casing_string")),
    )
    op.create_index(
        op.f("ix_casing_string_wellbore_id"), "casing_string", ["wellbore_id"], unique=False
    )
    op.create_index(
        op.f("ix_casing_string_document_id"), "casing_string", ["document_id"], unique=False
    )

    op.create_table(
        "cement_job",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("casing_id", sa.BigInteger(), nullable=False),
        sa.Column("toc_md_m", sa.Float(), nullable=True),
        sa.Column("toc_tvdss_m", sa.Float(), nullable=True),
        sa.Column("returns", sa.String(length=10), nullable=True),
        sa.Column("slurry_density_sg", sa.Float(), nullable=True),
        sa.Column("volume_m3", sa.Float(), nullable=True),
        sa.Column("bond_quality", sa.Text(), nullable=True),
        sa.Column("remedial", sa.Text(), nullable=True),
        *_evidence_columns("cement_job"),
        sa.CheckConstraint(in_list("returns", CEMENT_RETURNS), name=op.f("ck_cement_job_returns")),
        sa.ForeignKeyConstraint(
            ["casing_id"],
            ["casing_string.id"],
            name=op.f("fk_cement_job_casing_id_casing_string"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cement_job")),
    )
    op.create_index(op.f("ix_cement_job_casing_id"), "cement_job", ["casing_id"], unique=False)
    op.create_index(op.f("ix_cement_job_document_id"), "cement_job", ["document_id"], unique=False)

    op.create_table(
        "mud_interval",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("wellbore_id", sa.Integer(), nullable=False),
        sa.Column("md_from_m", sa.Float(), nullable=False),
        sa.Column("md_to_m", sa.Float(), nullable=False),
        sa.Column("tvdss_from_m", sa.Float(), nullable=True),
        sa.Column("tvdss_to_m", sa.Float(), nullable=True),
        sa.Column("hole_size_in", sa.Float(), nullable=True),
        sa.Column("mud_type", sa.String(length=40), nullable=True),
        sa.Column("mw_sg", sa.Float(), nullable=True),
        sa.Column("ecd_sg", sa.Float(), nullable=True),
        *_evidence_columns("mud_interval"),
        sa.ForeignKeyConstraint(
            ["wellbore_id"],
            ["wellbore.id"],
            name=op.f("fk_mud_interval_wellbore_id_wellbore"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mud_interval")),
    )
    op.create_index(
        "ix_mud_interval_wellbore_id_md_from_m",
        "mud_interval",
        ["wellbore_id", "md_from_m"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mud_interval_document_id"), "mud_interval", ["document_id"], unique=False
    )

    # ── DDR time log ──
    op.create_table(
        "ddr_operation",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("wellbore_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("t_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("t_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hours", sa.Float(), nullable=True),
        sa.Column("md_m", sa.Float(), nullable=True),
        sa.Column("activity_code", sa.String(length=40), nullable=True),
        sa.Column("phase", sa.String(length=30), nullable=True),
        sa.Column("description", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("is_npt", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("npt_category", sa.String(length=30), nullable=True),
        sa.Column("event_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "span_ids",
            postgresql.ARRAY(sa.BigInteger()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["wellbore_id"],
            ["wellbore.id"],
            name=op.f("fk_ddr_operation_wellbore_id_wellbore"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_ddr_operation_document_id_document"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["event.id"],
            name=op.f("fk_ddr_operation_event_id_event"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ddr_operation")),
    )
    op.create_index(
        "ix_ddr_operation_wellbore_id_t_from", "ddr_operation", ["wellbore_id", "t_from"]
    )
    op.create_index(
        op.f("ix_ddr_operation_document_id"), "ddr_operation", ["document_id"], unique=False
    )
    op.create_index(op.f("ix_ddr_operation_event_id"), "ddr_operation", ["event_id"], unique=False)

    # ── Review queue ──
    op.create_table(
        "review_item",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column("document_id", sa.BigInteger(), nullable=True),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column(
            "span_ids",
            postgresql.ARRAY(sa.BigInteger()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("field", sa.String(length=60), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "proposed",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=10), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("decided_by", sa.String(length=100), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correction", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(in_list("kind", REVIEW_KINDS), name=op.f("ck_review_item_kind")),
        sa.CheckConstraint(in_list("status", REVIEW_STATUSES), name=op.f("ck_review_item_status")),
        _confidence("review_item"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_review_item_document_id_document"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_item")),
    )
    op.create_index("ix_review_item_status_kind", "review_item", ["status", "kind"], unique=False)
    op.create_index(
        op.f("ix_review_item_document_id"), "review_item", ["document_id"], unique=False
    )


def downgrade() -> None:
    op.drop_table("review_item")
    op.drop_table("ddr_operation")
    op.drop_table("mud_interval")
    op.drop_table("cement_job")
    op.drop_table("casing_string")
    op.drop_table("mitigation")
    op.drop_table("event_evidence")
    op.drop_table("event")
    for column in ("indexed_at", "extracted_at", "extract_error"):
        op.drop_column("document", column)
    for stage in ("index_status", "extract_status"):
        op.drop_index(op.f(f"ix_document_{stage}"), table_name="document")
        op.drop_constraint(op.f(f"ck_document_{stage}"), "document", type_="check")
        op.drop_column("document", stage)
    op.drop_constraint(op.f("ck_well_fluid_type"), "well", type_="check")
    op.drop_column("well", "fluid_type")
