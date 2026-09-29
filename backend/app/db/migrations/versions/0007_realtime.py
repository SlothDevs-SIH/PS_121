"""B4: real-time drilling data - rt_sample and rt_score hypertables (wide, one row per
wellbore and timestamp), channel mapping and replay sessions.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.vocab import REPLAY_STATUSES, RIG_STATES, in_list

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHANNELS = (
    "bit_depth_m",
    "hole_depth_m",
    "hookload_kn",
    "wob_kn",
    "rpm",
    "torque_knm",
    "spp_kpa",
    "flow_in_lpm",
    "flow_out_lpm",
    "pit_volume_m3",
    "rop_m_h",
    "gas_pct",
)


def upgrade() -> None:
    op.create_table(
        "rt_sample",
        sa.Column("wellbore_id", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        *[sa.Column(c, sa.Float(), nullable=True) for c in CHANNELS],
        sa.Column("quality", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("wellbore_id", "ts", name=op.f("pk_rt_sample")),
    )
    op.create_table(
        "rt_score",
        sa.Column("wellbore_id", sa.Integer(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rig_state", sa.String(length=20), nullable=False),
        sa.Column("bit_depth_m", sa.Float(), nullable=True),
        sa.Column("formation", sa.Text(), nullable=True),
        sa.Column("indicators", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dejavu", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(in_list("rig_state", RIG_STATES), name=op.f("ck_rt_score_rig_state")),
        sa.PrimaryKeyConstraint("wellbore_id", "ts", name=op.f("pk_rt_score")),
    )
    # TimescaleDB-specific: time partitioning (1-day chunks) and compression after 7 days,
    # segmented by wellbore so one well's history decompresses on its own.
    for table in ("rt_sample", "rt_score"):
        op.execute(
            f"SELECT create_hypertable('{table}', 'ts', chunk_time_interval => INTERVAL '1 day')"
        )
        op.execute(
            f"ALTER TABLE {table} SET (timescaledb.compress, "
            "timescaledb.compress_segmentby = 'wellbore_id')"
        )
        op.execute(f"SELECT add_compression_policy('{table}', INTERVAL '7 days')")
    op.create_table(
        "channel_mapping",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("mnemonic", sa.String(length=40), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channel_mapping")),
        sa.UniqueConstraint("source", "mnemonic", name=op.f("uq_channel_mapping_source")),
    )
    op.create_table(
        "replay_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("well_id", sa.Integer(), nullable=False),
        sa.Column("wellbore_id", sa.Integer(), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=False),
        sa.Column("speed", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=True),
        sa.Column("data_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_now", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            in_list("status", REPLAY_STATUSES), name=op.f("ck_replay_session_status")
        ),
        sa.ForeignKeyConstraint(
            ["well_id"],
            ["well.id"],
            name=op.f("fk_replay_session_well_id_well"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["wellbore_id"],
            ["wellbore.id"],
            name=op.f("fk_replay_session_wellbore_id_wellbore"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_replay_session")),
    )


def downgrade() -> None:
    op.drop_table("replay_session")
    op.drop_table("channel_mapping")
    op.drop_table("rt_score")
    op.drop_table("rt_sample")
