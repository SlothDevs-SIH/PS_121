"""B2 foundation without a database: vocabularies, the pgvector column type, statements
compiled with the PostgreSQL dialect, schema shapes, settings and Celery task stubs."""

import math
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import insert, select
from sqlalchemy.dialects import postgresql

from app.api.v1.params import BBox, parse_bbox
from app.api.v1.routes.documents import event_counts_stmt
from app.api.v1.schemas.common import EvidenceRef
from app.api.v1.schemas.documents import DocumentSummary
from app.api.v1.schemas.events import EventCreate, EventParams
from app.api.v1.schemas.review import ReviewCorrect
from app.api.v1.schemas.wells import OffsetsOut, WellDetail
from app.core.config import Settings
from app.db.models import Chunk, Document, Event, Well
from app.db.models.documents import EMBEDDING_DIM
from app.db.types import Vector
from app.db.vocab import ACTION_CODES, EVENT_TYPES, in_list

PG = postgresql.dialect()
MIGRATIONS = Path(__file__).resolve().parents[2] / "app" / "db" / "migrations" / "versions"


def _sql(stmt: object) -> str:
    return str(stmt.compile(dialect=PG))  # type: ignore[attr-defined]


# ── vocabularies ──


def test_event_taxonomy_is_the_master_plan_list() -> None:
    assert EVENT_TYPES == (
        "LOSS", "KICK", "STUCK", "TIGHT", "TORQUE", "INSTAB", "BALLING", "OVERP",
        "GAS", "CEMENT", "CASING", "FISH", "EQUIP", "WAIT", "OTHER_NPT",
    )  # fmt: skip
    assert len(set(ACTION_CODES)) == len(ACTION_CODES)
    assert {"LCM_PILL_COARSE", "JAR_UP", "DRILLERS_METHOD", "TOP_JOB", "OTHER"} <= set(ACTION_CODES)


def test_in_list_renders_a_quoted_check() -> None:
    assert in_list("severity", ("low", "high")) == "severity IN ('low', 'high')"


def test_vocab_matches_migrations() -> None:
    """Revision 0005 renders its CHECK constraints from app.db.vocab, so editing a
    vocabulary would silently change what an already-applied revision means. This snapshot
    fails on any edit: add a migration that alters the CHECK, then update the snapshot."""
    from app.db import vocab

    snapshot = {
        "SEVERITIES": ("low", "medium", "high"),
        "EVENT_SOURCES": ("rules", "llm", "manual", "import"),
        "EVENT_STATUSES": ("active", "rejected"),
        "EVIDENCE_ROLES": ("primary", "supporting"),
        "MITIGATION_OUTCOMES": ("success", "partial", "fail", "unknown"),
        "CEMENT_RETURNS": ("full", "partial", "none"),
        "FLUID_TYPES": ("oil", "gas", "water"),
        "STAGE_STATUSES": ("pending", "running", "done", "failed", "skipped"),
        "REVIEW_KINDS": ("event", "mitigation", "casing", "cement", "mud", "alias", "other"),
        "REVIEW_STATUSES": ("pending", "accepted", "corrected", "rejected"),
    }
    text = (MIGRATIONS / "0005_engineering_records.py").read_text(encoding="utf-8")
    for name, values in snapshot.items():
        assert getattr(vocab, name) == values, f"{name} changed: needs a new migration"
        assert name in text
    assert len(EVENT_TYPES) == 15 and "EVENT_TYPES" in text


# ── pgvector column type ──


def test_vector_ddl_and_bind_cast() -> None:
    assert Vector(1024).get_col_spec() == "vector(1024)"
    stmt = insert(Chunk).values(
        document_id=1, page_from=1, page_to=1, span_ids=[1], text="x", embedding=[0.0] * 1024
    )
    assert "CAST(%(embedding)s AS vector(1024))" in _sql(stmt)


def test_vector_bind_and_result_processing() -> None:
    v = Vector(3)
    bind = v.bind_processor(PG)
    assert bind([1, 0.5, -2]) == "[1.0,0.5,-2.0]"
    assert bind(None) is None
    with pytest.raises(ValueError, match="3-dimensional"):
        bind([1.0, 2.0])
    with pytest.raises(ValueError, match="finite"):
        bind([1.0, math.nan, 0.0])
    result = v.result_processor(PG, None)
    assert result("[1,0.5,-2]") == [1.0, 0.5, -2.0]
    assert result("[]") == []
    assert result(None) is None
    with pytest.raises(ValueError, match="positive"):
        Vector(0)


def test_chunk_search_columns() -> None:
    cols = Chunk.__table__.c
    assert EMBEDDING_DIM == 1024
    assert cols.tsv.computed is not None and cols.tsv.computed.persisted
    assert "to_tsvector('english', text)" in str(cols.tsv.computed.sqltext)
    # Neither search column is loaded by a plain ORM select (they are deferred).
    assert "embedding" not in _sql(select(Chunk)) and "tsv" not in _sql(select(Chunk))


def test_cosine_distance_operator_compiles() -> None:
    q = [0.1] * EMBEDDING_DIM
    stmt = select(Chunk.id).order_by(Chunk.embedding.op("<=>")(q)).limit(5)
    sql = _sql(stmt)
    assert "chunk.embedding <=> CAST(%(embedding_1)s AS vector(1024))" in sql


# ── statements and models ──


def test_event_count_statement() -> None:
    sql = re.sub(r"\s+", " ", _sql(event_counts_stmt([1, 2])))
    assert "count(DISTINCT event_evidence.event_id)" in sql
    assert "JOIN event ON event.id = event_evidence.event_id" in sql
    assert "event_evidence.document_id IN (__[POSTCOMPILE_document_id_1])" in sql
    assert "event.status = %(status_1)s" in sql
    assert "GROUP BY event_evidence.document_id" in sql


def test_new_columns_on_existing_tables() -> None:
    assert Well.__table__.c.fluid_type.nullable
    doc = Document.__table__.c
    assert doc.extract_status.server_default is not None
    assert not doc.extract_status.nullable and not doc.index_status.nullable
    assert Event.__table__.c.params.server_default is not None


# ── schemas ──


def test_b1_callers_still_validate_without_b2_fields() -> None:
    """The B1 services build these without the B2 keys; the defaults keep them valid."""
    doc = DocumentSummary(
        id=1, filename="a.pdf", doc_type=None, well_id=None, well_name=None,
        raw_well_name=None, report_date=None, page_count=1, ingest_status="processed",
        error=None, synthetic=True, size_bytes=10, created_at=datetime.now(tz=UTC),
        processed_at=None,
    )  # fmt: skip
    assert (doc.extract_status, doc.index_status, doc.event_count) == ("pending", "pending", 0)
    out = OffsetsOut(well_id=1, mode="SURFACE", radius_km=5, formation=None, offsets=[])
    assert out.excluded == [] and out.distance_label.startswith("Surface")
    fields = WellDetail.model_fields
    for name in ("casing", "mud", "event_counts", "recent_events", "documents", "lessons"):
        assert not fields[name].is_required()


def test_response_schemas_mark_defaults_required() -> None:
    schema = OffsetsOut.model_json_schema(mode="serialization")
    assert {"excluded", "distance_label", "tvdss_from_m"} <= set(schema["required"])
    assert set(EventParams.model_json_schema(mode="serialization")["required"]) == set(
        EventParams.model_fields
    )
    assert "filename" in EvidenceRef.model_json_schema(mode="serialization")["required"]


def test_event_create_rejects_unknown_param_keys() -> None:
    base = {"well_id": 1, "event_type": "LOSS"}
    assert EventCreate.model_validate(base).params.loss_rate_m3_h is None
    with pytest.raises(ValidationError):
        EventCreate.model_validate({**base, "params": {"loss_rate_bbl_h": 3}})


def test_review_correct_needs_fields() -> None:
    assert ReviewCorrect(action="correct", fields={"md_m": 1850}).fields == {"md_m": 1850}
    with pytest.raises(ValidationError):
        ReviewCorrect(action="correct", fields={})


def test_parse_bbox() -> None:
    assert parse_bbox(None) is None
    assert parse_bbox("94.9,27.1,95.4,27.6") == BBox(94.9, 27.1, 95.4, 27.6)


# ── settings and tasks ──


def test_b2_settings_defaults_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    s = Settings()
    assert s.llm_base_url is None and s.llm_model == "qwen2.5:7b-instruct"
    assert s.llm_timeout_s == 60 and s.extract_llm_enabled is False
    assert s.extract_confidence_threshold == 0.75
    assert (s.embedding_provider, s.embedding_model) == ("hash", "bge-m3")
    assert s.embedding_base_url is None and s.reranker_url is None
    monkeypatch.setenv("SMRITI_EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setenv("SMRITI_EXTRACT_CONFIDENCE_THRESHOLD", "0.6")
    s = Settings()
    assert s.embedding_provider == "ollama" and s.extract_confidence_threshold == 0.6
    monkeypatch.setenv("SMRITI_EMBEDDING_PROVIDER", "openai")
    with pytest.raises(ValidationError):
        Settings()


def test_b2_tasks_are_registered_on_the_extract_queue() -> None:
    from app.extract.tasks import process_document_task
    from app.search.tasks import index_document_task
    from app.workers.celery_app import celery_app

    assert process_document_task.name == "extract.process_document"
    assert index_document_task.name == "search.index_document"
    for task in (process_document_task, index_document_task):
        assert task.queue == "extract"
        assert task.max_retries == 3  # transient DB/S3/embedder errors are retried
    assert {"app.extract.tasks", "app.search.tasks"} <= set(celery_app.conf.include)
