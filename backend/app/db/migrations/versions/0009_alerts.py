"""B4: alerts (S9) and their feedback.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.vocab import (
    ALERT_SEVERITIES,
    ALERT_STATUSES,
    ALERT_TYPES,
    ALERT_VERDICTS,
    in_list,
)

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "alert",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("well_id", sa.Integer(), nullable=False),
        sa.Column("wellbore_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("alert_type", sa.String(length=20), nullable=False),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("score_kind", sa.String(length=12), nullable=False),
        sa.Column("md_m", sa.Float(), nullable=True),
        sa.Column("tvdss_m", sa.Float(), nullable=True),
        sa.Column("formation", sa.Text(), nullable=True),
        sa.Column("t_data", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sources", JSON, nullable=False),
        sa.Column("evidence", JSON, nullable=False),
        sa.Column("drivers", JSON, nullable=False),
        sa.Column("recommendations", JSON, nullable=False),
        sa.Column("detail", JSON, nullable=False),
        sa.Column("budget_exempt", sa.Boolean(), nullable=False),
        sa.Column("acked_by", sa.Text(), nullable=True),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismiss_reason", sa.Text(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(in_list("alert_type", ALERT_TYPES), name=op.f("ck_alert_alert_type")),
        sa.CheckConstraint(in_list("severity", ALERT_SEVERITIES), name=op.f("ck_alert_severity")),
        sa.CheckConstraint(in_list("status", ALERT_STATUSES), name=op.f("ck_alert_status")),
        # No citation, no claim (master plan P1): an alert without evidence cannot be stored.
        sa.CheckConstraint("jsonb_array_length(evidence) >= 1", name=op.f("ck_alert_has_evidence")),
        sa.ForeignKeyConstraint(
            ["well_id"], ["well.id"], name=op.f("fk_alert_well_id_well"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert")),
    )
    op.create_index("ix_alert_well_id_status", "alert", ["well_id", "status"])
    op.create_table(
        "alert_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alert_id", sa.BigInteger(), nullable=False),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            in_list("verdict", ALERT_VERDICTS), name=op.f("ck_alert_feedback_verdict")
        ),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["alert.id"],
            name=op.f("fk_alert_feedback_alert_id_alert"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_feedback")),
    )


def downgrade() -> None:
    op.drop_table("alert_feedback")
    op.drop_index("ix_alert_well_id_status", table_name="alert")
    op.drop_table("alert")
