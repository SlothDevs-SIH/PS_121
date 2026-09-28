"""B0: enable the PostgreSQL extensions the whole platform relies on.

postgis     — well locations, 3D wellbore paths, radius queries (S4)
vector      — pgvector embeddings for semantic search (S5)
timescaledb — hypertables for real-time drilling channels (S12)
pg_trgm     — trigram similarity for well-name aliasing and fuzzy search (S3/S5)

Revision ID: 0001
Revises:
Create Date: 2026-09-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXTENSIONS = ["postgis", "vector", "timescaledb", "pg_trgm"]


def upgrade() -> None:
    for ext in EXTENSIONS:
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {ext}")


def downgrade() -> None:
    for ext in reversed(EXTENSIONS):
        op.execute(f"DROP EXTENSION IF EXISTS {ext}")
