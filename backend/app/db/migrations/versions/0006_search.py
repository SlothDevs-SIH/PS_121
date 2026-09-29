"""B2: hybrid-search columns on chunk - dense embedding (pgvector, HNSW) and lexical tsvector
(generated, GIN), plus the embedder id that produced each vector.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.types import Vector

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 1024  # app.db.models.documents.EMBEDDING_DIM at the time of this revision


def upgrade() -> None:
    op.add_column("chunk", sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True))
    op.add_column(
        "chunk",
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', text)", persisted=True),
            nullable=True,
        ),
    )
    op.add_column("chunk", sa.Column("embedded_with", sa.String(length=100), nullable=True))
    op.create_index("ix_chunk_tsv", "chunk", ["tsv"], unique=False, postgresql_using="gin")
    # pgvector-specific: HNSW approximate-nearest-neighbour index for cosine distance (<=>).
    # Needs pgvector >= 0.5 (the compose image ships 0.8.6). Default build parameters
    # (m = 16, ef_construction = 64) are fine at this corpus size.
    op.execute(
        "CREATE INDEX ix_chunk_embedding_hnsw ON chunk USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunk_embedding_hnsw")
    op.drop_index("ix_chunk_tsv", table_name="chunk")
    op.drop_column("chunk", "embedded_with")
    op.drop_column("chunk", "tsv")
    op.drop_column("chunk", "embedding")
