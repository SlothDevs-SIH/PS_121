"""Render the Alembic migrations as SQL in offline mode (no database connection) and check
the B2 DDL, plus that the migrations and the ORM metadata describe the same schema."""

import io
import re
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.db import models  # noqa: F401  (registers every table)
from app.db.base import Base
from app.db.vocab import EVENT_TYPES, REVIEW_KINDS, STAGE_STATUSES

BACKEND = Path(__file__).resolve().parents[2]
B2_TABLES = (
    "event",
    "event_evidence",
    "mitigation",
    "casing_string",
    "cement_job",
    "mud_interval",
    "ddr_operation",
    "review_item",
)


def _render(revisions: str, *, downgrade: bool = False) -> str:
    """``alembic upgrade|downgrade <revisions> --sql``: SQL text only, no connection."""
    buf = io.StringIO()
    cfg = Config(str(BACKEND / "alembic.ini"), output_buffer=buf)
    (command.downgrade if downgrade else command.upgrade)(cfg, revisions, sql=True)
    return buf.getvalue()


@pytest.fixture(scope="module")
def upgrade_sql() -> str:
    return _render("head")


@pytest.fixture(scope="module")
def b2_sql() -> str:
    return _render("0004:head")


def _normalise(sql: str) -> str:
    return re.sub(r"\s+", " ", sql)


def test_full_upgrade_renders_every_revision(upgrade_sql: str) -> None:
    for rev in ("0001", "0002", "0003", "0004", "0005", "0006"):
        assert f"version_num='{rev}'" in upgrade_sql or f"VALUES ('{rev}')" in upgrade_sql


def test_b2_tables_and_constraints(b2_sql: str) -> None:
    sql = _normalise(b2_sql)
    for table in B2_TABLES:
        assert f"CREATE TABLE {table} (" in sql
    types = ", ".join(f"'{t}'" for t in EVENT_TYPES)
    assert f"CONSTRAINT ck_event_event_type CHECK (event_type IN ({types}))" in sql
    assert "CONSTRAINT ck_event_severity CHECK (severity IN ('low', 'medium', 'high'))" in sql
    kinds = ", ".join(f"'{k}'" for k in REVIEW_KINDS)
    assert f"CONSTRAINT ck_review_item_kind CHECK (kind IN ({kinds}))" in sql
    assert "PRIMARY KEY (event_id, span_id)" in sql
    assert (
        "FOREIGN KEY(event_id) REFERENCES event (id) ON DELETE SET NULL" in sql
    )  # ddr_operation keeps its line when the event is deleted
    assert "FOREIGN KEY(formation_id) REFERENCES formation (id) ON DELETE SET NULL" in sql
    assert "CREATE INDEX ix_event_well_id_md_m ON event (well_id, md_m)" in sql
    assert "CREATE INDEX ix_event_event_type ON event (event_type)" in sql
    assert "CREATE INDEX ix_event_formation_id ON event (formation_id)" in sql
    assert "CREATE INDEX ix_review_item_status_kind ON review_item (status, kind)" in sql


def test_b2_changes_to_existing_tables(b2_sql: str) -> None:
    sql = _normalise(b2_sql)
    assert "ALTER TABLE well ADD COLUMN fluid_type VARCHAR(10)" in sql
    assert "CHECK (fluid_type IN ('oil', 'gas', 'water'))" in sql
    statuses = ", ".join(f"'{s}'" for s in STAGE_STATUSES)
    for stage in ("extract_status", "index_status"):
        added = f"ALTER TABLE document ADD COLUMN {stage} VARCHAR(10) DEFAULT 'pending' NOT NULL"
        assert added in sql
        assert f"CHECK ({stage} IN ({statuses}))" in sql
    for column in ("extract_error TEXT", "extracted_at TIMESTAMP", "indexed_at TIMESTAMP"):
        assert f"ALTER TABLE document ADD COLUMN {column}" in sql


def test_search_columns_and_indexes(b2_sql: str) -> None:
    sql = _normalise(b2_sql)
    assert "ALTER TABLE chunk ADD COLUMN embedding vector(1024)" in sql
    assert (
        "ALTER TABLE chunk ADD COLUMN tsv TSVECTOR GENERATED ALWAYS AS "
        "(to_tsvector('english', text)) STORED" in sql
    )
    assert "ALTER TABLE chunk ADD COLUMN embedded_with VARCHAR(100)" in sql
    assert "CREATE INDEX ix_chunk_tsv ON chunk USING gin (tsv)" in sql
    assert (
        "CREATE INDEX ix_chunk_embedding_hnsw ON chunk USING hnsw (embedding vector_cosine_ops)"
        in sql
    )


def test_downgrade_reverses_b2() -> None:
    sql = _normalise(_render("0006:0004", downgrade=True))
    assert "DROP INDEX IF EXISTS ix_chunk_embedding_hnsw" in sql
    for table in B2_TABLES:
        assert f"DROP TABLE {table};" in sql
    assert "ALTER TABLE well DROP COLUMN fluid_type" in sql
    assert "ALTER TABLE document DROP COLUMN extract_status" in sql
    assert "ALTER TABLE chunk DROP COLUMN embedding" in sql


def _create_table_columns(sql: str, table: str) -> set[str]:
    body = re.search(rf"CREATE TABLE {table} \((.*?)\n\);", sql, re.S)
    assert body, f"no CREATE TABLE {table}"
    cols = set()
    for line in body.group(1).splitlines():
        line = line.strip()
        if line and not line.startswith(("CONSTRAINT", "PRIMARY KEY", "UNIQUE", "FOREIGN")):
            cols.add(line.split()[0])
    return cols


def test_migrations_match_orm_metadata(upgrade_sql: str) -> None:
    """Every ORM column exists in the migrations (catches a model edit without a revision)."""
    added = {
        (m.group(1), m.group(2))
        for m in re.finditer(r"ALTER TABLE (\w+) ADD COLUMN (\w+)", upgrade_sql)
    }
    for table in Base.metadata.sorted_tables:
        created = _create_table_columns(upgrade_sql, table.name)
        for column in table.columns:
            assert column.name in created or (table.name, column.name) in added, (
                f"{table.name}.{column.name} is in the ORM but in no migration"
            )


def test_orm_indexes_exist_in_migrations(upgrade_sql: str) -> None:
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            assert f"CREATE INDEX {index.name} ON {table.name}" in upgrade_sql, index.name
