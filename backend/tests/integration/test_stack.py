"""Run against the docker compose stack:  docker compose up -d --wait && pytest -m integration

The API URL defaults to http://localhost:8000; database/redis/S3 settings come from the
same SMRITI_* variables as the app (defaults match docker-compose.yml's published ports).
"""

import os
import uuid

import httpx
import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine
from app.storage.s3 import get_s3_client

pytestmark = pytest.mark.integration

API = os.environ.get("SMRITI_API_URL", "http://localhost:8000")


def _alembic_head() -> str:
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    assert head is not None
    return head


def test_api_is_ready() -> None:
    r = httpx.get(f"{API}/readyz", timeout=10)
    assert r.status_code == 200, r.text
    assert {c["name"]: c["ok"] for c in r.json()["components"]} == {
        "postgres": True,
        "redis": True,
        "object_storage": True,
    }


def test_required_extensions_installed_and_migration_at_head() -> None:
    with get_engine().connect() as conn:
        exts = set(conn.execute(text("SELECT extname FROM pg_extension")).scalars())
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        # Each extension actually works, not just installed:
        conn.execute(text("SELECT ST_AsText(ST_MakePoint(95.3, 27.3))")).scalar_one()
        conn.execute(text("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector")).scalar_one()
        conn.execute(text("SELECT extversion FROM pg_extension WHERE extname='timescaledb'"))
        conn.execute(text("SELECT similarity('HAPJAN-12', 'HPJ-12')")).scalar_one()
    assert set(get_settings().required_pg_extensions) <= exts
    assert version == _alembic_head()


def test_object_storage_round_trip() -> None:
    s3 = get_s3_client()
    key = f"integration/{uuid.uuid4().hex}.txt"
    bucket = get_settings().s3_bucket_raw
    s3.put_object(Bucket=bucket, Key=key, Body=b"smriti")
    try:
        assert s3.get_object(Bucket=bucket, Key=key)["Body"].read() == b"smriti"
    finally:
        s3.delete_object(Bucket=bucket, Key=key)


def test_celery_worker_round_trip() -> None:
    from app.workers.celery_app import ping

    assert "pong" in ping.delay().get(timeout=20)


def test_built_endpoint_through_real_server() -> None:
    # The last skeleton (the Offset Risk Brief) was built in B5: a PDF through the real server.
    well = httpx.get(f"{API}/api/v1/wells", params={"limit": 1}, timeout=10).json()["items"][0]
    r = httpx.get(f"{API}/api/v1/reports/offset-brief/{well['id']}", timeout=60)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
