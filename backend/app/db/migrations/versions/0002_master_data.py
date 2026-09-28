"""B1: well master data - fields, formations, wells, wellbores, formation tops.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.types import Geography, Geometry

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "field",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("basin", sa.Text(), nullable=True),
        sa.Column("crs_epsg", sa.Integer(), nullable=False),
        sa.Column("synthetic", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_field")),
        sa.UniqueConstraint("name", name=op.f("uq_field_name")),
    )
    op.create_table(
        "formation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("basin", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("synonyms", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("strat_order", sa.Integer(), nullable=False),
        sa.Column("lithology", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_formation")),
        sa.UniqueConstraint("basin", "name", name=op.f("uq_formation_basin")),
    )
    op.create_table(
        "well",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("aliases", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("field_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("well_type", sa.String(length=30), nullable=True),
        sa.Column("profile", sa.String(length=20), nullable=True),
        sa.Column("surface_loc", Geography("POINT", 4326), nullable=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("rkb_elev_m", sa.Float(), nullable=True),
        sa.Column("gl_elev_m", sa.Float(), nullable=True),
        sa.Column("datum_assumed", sa.Boolean(), nullable=False),
        sa.Column("spud_date", sa.Date(), nullable=True),
        sa.Column("completion_date", sa.Date(), nullable=True),
        sa.Column("td_md_m", sa.Float(), nullable=True),
        sa.Column("rig_name", sa.Text(), nullable=True),
        sa.Column("units_system", sa.String(length=20), nullable=True),
        sa.Column("synthetic", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["field_id"], ["field.id"], name=op.f("fk_well_field_id_field")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_well")),
        sa.UniqueConstraint("canonical_name", name=op.f("uq_well_canonical_name")),
    )
    op.create_table(
        "wellbore",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("well_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("trajectory_assumed", sa.Boolean(), nullable=False),
        sa.Column("td_md_m", sa.Float(), nullable=True),
        sa.Column("path_geom", Geometry("LINESTRINGZ"), nullable=True),
        sa.ForeignKeyConstraint(
            ["well_id"], ["well.id"], name=op.f("fk_wellbore_well_id_well"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wellbore")),
    )
    op.create_index(op.f("ix_wellbore_well_id"), "wellbore", ["well_id"], unique=False)
    op.create_table(
        "formation_top",
        sa.Column("wellbore_id", sa.Integer(), nullable=False),
        sa.Column("formation_id", sa.Integer(), nullable=False),
        sa.Column("top_md_m", sa.Float(), nullable=False),
        sa.Column("top_tvd_m", sa.Float(), nullable=False),
        sa.Column("top_tvdss_m", sa.Float(), nullable=False),
        sa.Column("entry_point", Geometry("POINTZ"), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(
            ["formation_id"], ["formation.id"], name=op.f("fk_formation_top_formation_id_formation")
        ),
        sa.ForeignKeyConstraint(
            ["wellbore_id"],
            ["wellbore.id"],
            name=op.f("fk_formation_top_wellbore_id_wellbore"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("wellbore_id", "formation_id", name=op.f("pk_formation_top")),
    )


def downgrade() -> None:
    op.drop_table("formation_top")
    op.drop_table("wellbore")
    op.drop_table("well")
    op.drop_table("formation")
    op.drop_table("field")
