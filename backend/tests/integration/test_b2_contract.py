"""B2 schema additions against the migrated, seeded stack (runs in GitHub CI).

These check shapes that stay true while the B2 features land: the new document stage
columns exist and are served, the event-count query runs against the real event tables,
and the B1 endpoints carry their additive B2 fields.
"""

import os

import httpx
import pytest

from app.db.vocab import STAGE_STATUSES

pytestmark = pytest.mark.integration

API = os.environ.get("SMRITI_API_URL", "http://localhost:8000")


def _get(path: str, **params: object) -> httpx.Response:
    r = httpx.get(f"{API}{path}", params=params, timeout=30)
    assert r.status_code == 200, r.text
    return r


def test_documents_carry_stage_fields_and_event_counts() -> None:
    items = _get("/api/v1/documents", limit=20).json()["items"]
    assert items, "expected seeded documents"
    for doc in items:
        assert doc["extract_status"] in STAGE_STATUSES
        assert doc["index_status"] in STAGE_STATUSES
        assert isinstance(doc["event_count"], int) and doc["event_count"] >= 0
    detail = _get(f"/api/v1/documents/{items[0]['id']}").json()
    assert detail["event_count"] == items[0]["event_count"]
    pending = _get("/api/v1/documents", extract_status="pending", limit=500).json()["items"]
    assert all(d["extract_status"] == "pending" for d in pending)


def test_well_detail_and_offsets_have_b2_fields() -> None:
    wells = _get("/api/v1/wells").json()["items"]
    assert all("fluid_type" in w for w in wells)
    wid = wells[0]["id"]
    detail = _get(f"/api/v1/wells/{wid}").json()
    for key in ("casing", "mud", "event_counts", "recent_events", "documents", "lessons"):
        assert key in detail
    offsets = _get(f"/api/v1/wells/{wid}/offsets", radius_km=25).json()
    assert offsets["mode"] == "SURFACE"
    assert offsets["distance_label"] and isinstance(offsets["excluded"], list)
