"""B1: survey stations, plus spatial (GiST) and trigram indexes.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "survey_station",
        sa.Column("wellbore_id", sa.Integer(), nullable=False),
        sa.Column("md_m", sa.Float(), nullable=False),
        sa.Column("inc_deg", sa.Float(), nullable=False),
        sa.Column("azi_deg", sa.Float(), nullable=False),
        sa.Column("tvd_m", sa.Float(), nullable=False),
        sa.Column("tvdss_m", sa.Float(), nullable=False),
        sa.Column("north_m", sa.Float(), nullable=False),
        sa.Column("east_m", sa.Float(), nullable=False),
        sa.Column("dls_deg_30m", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["wellbore_id"],
            ["wellbore.id"],
            name=op.f("fk_survey_station_wellbore_id_wellbore"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("wellbore_id", "md_m", name=op.f("pk_survey_station")),
    )
    op.execute("CREATE INDEX ix_well_surface_loc ON well USING gist (surface_loc)")
    op.execute("CREATE INDEX ix_wellbore_path_geom ON wellbore USING gist (path_geom)")
    op.execute(
        "CREATE INDEX ix_formation_top_entry_point ON formation_top USING gist (entry_point)"
    )
    op.execute("CREATE INDEX ix_well_name_trgm ON well USING gin (canonical_name gin_trgm_ops)")


def downgrade() -> None:
    for ix in (
        "ix_well_name_trgm",
        "ix_formation_top_entry_point",
        "ix_wellbore_path_geom",
        "ix_well_surface_loc",
    ):
        op.execute(f"DROP INDEX IF EXISTS {ix}")
    op.drop_table("survey_station")
