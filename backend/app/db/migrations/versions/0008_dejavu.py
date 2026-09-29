"""B4: Déjà Vu signature library (S7d) - the real-time window before each historical event.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pattern_signature",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=True),
        sa.Column("well_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("formation", sa.Text(), nullable=True),
        sa.Column("hole_size_in", sa.Float(), nullable=True),
        sa.Column("md_m", sa.Float(), nullable=True),
        sa.Column("tvdss_m", sa.Float(), nullable=True),
        sa.Column("dt_s", sa.Integer(), nullable=False),
        sa.Column("channels", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("drilling_share", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["event.id"],
            name=op.f("fk_pattern_signature_event_id_event"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["well_id"],
            ["well.id"],
            name=op.f("fk_pattern_signature_well_id_well"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pattern_signature")),
    )


def downgrade() -> None:
    op.drop_table("pattern_signature")
