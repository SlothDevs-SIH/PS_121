"""B1 endpoints against the running stack (needs `app.cli seed` to have run)."""

import io
import math
import os
import time
import uuid

import httpx
import pytest
from fpdf import FPDF

pytestmark = pytest.mark.integration

API = os.environ.get("SMRITI_API_URL", "http://localhost:8000")


def _get(path: str, **params: object) -> httpx.Response:
    return httpx.get(f"{API}{path}", params=params, timeout=30)


def _well_id(name: str) -> int:
    items = _get("/api/v1/wells", q=name).json()["items"]
    match = [w for w in items if w["name"] == name]
    assert match, f"{name} not seeded"
    return int(match[0]["id"])


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def test_wells_are_seeded_with_synthetic_flag() -> None:
    body = _get("/api/v1/wells").json()
    assert body["total"] >= 3
    assert all(w["synthetic"] for w in body["items"])
    statuses = {w["status"] for w in body["items"]}
    assert {"completed", "planned"} <= statuses


def test_surface_offsets_match_independent_distance() -> None:
    wid = _well_id("SYN-ASM-01")
    me = _get(f"/api/v1/wells/{wid}").json()
    body = _get(f"/api/v1/wells/{wid}/offsets", radius_km=25).json()
    offsets = body["offsets"]
    assert offsets, "expected offset wells within 25 km"
    dists = [o["distance_m"] for o in offsets]
    assert dists == sorted(dists)
    assert all(d <= 25_000 for d in dists)
    for o in offsets:
        ref = _haversine_m(me["lat"], me["lon"], o["lat"], o["lon"])
        assert o["distance_m"] == pytest.approx(ref, rel=0.006, abs=1.0)  # spheroid vs sphere
    small = _get(f"/api/v1/wells/{wid}/offsets", radius_km=0.2).json()["offsets"]
    assert all(o["distance_m"] <= 200 for o in small)


def test_trajectory_and_well_detail() -> None:
    wid = _well_id("SYN-ASM-02")
    traj = _get(f"/api/v1/wells/{wid}/trajectory").json()
    stations = traj["stations"]
    assert all(s["tvd_m"] <= s["md_m"] + 1e-6 for s in stations)
    detail = _get(f"/api/v1/wells/{wid}").json()
    assert traj["path"][0]["lat"] == pytest.approx(detail["lat"], abs=1e-6)
    assert traj["path"][0]["lon"] == pytest.approx(detail["lon"], abs=1e-6)
    tops = detail["formation_tops"]
    assert [t["top_md_m"] for t in tops] == sorted(t["top_md_m"] for t in tops)
    assert all(
        t["top_tvdss_m"] == pytest.approx(t["top_tvd_m"] - detail["rkb_elev_m"], abs=0.2)
        for t in tops
    )
    assert 0 <= detail["data_quality"]["score"] <= 1
    assert _get("/api/v1/formations").json()[0]["strat_order"] == 1


def test_unknown_well_is_404_and_unbuilt_route_is_501() -> None:
    assert _get("/api/v1/wells/999999").json()["error"]["code"] == "not_found"
    r = _get("/api/v1/wells/1/risk-profile")
    assert r.status_code == 501 and r.json()["error"]["details"]["phase"] == "B3"


def _unique_ddr() -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in (
        "DAILY DRILLING REPORT",
        "SYNTHETIC DATA - NOT OIL INDIA DATA",
        "Well: SYN-ASM-01    Rig: Rig SYN-1    Report No: 99    Date: 2020-01-02",
        f"Integration test nonce {uuid.uuid4().hex}",
    ):
        pdf.cell(0, 8, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def test_upload_process_and_page_evidence() -> None:
    data = _unique_ddr()
    files = {"files": ("it_ddr.pdf", io.BytesIO(data), "application/pdf")}
    first = httpx.post(f"{API}/api/v1/documents", files=files, timeout=30)
    assert first.status_code == 202, first.text
    doc_id = first.json()[0]["document_id"]
    assert first.json()[0]["duplicate"] is False

    deadline = time.monotonic() + 90
    while True:
        doc = _get(f"/api/v1/documents/{doc_id}").json()
        if doc["ingest_status"] not in ("queued", "processing"):
            break
        assert time.monotonic() < deadline, "worker did not process the upload"
        time.sleep(1)
    assert doc["ingest_status"] == "processed", doc
    assert doc["doc_type"] == "DDR"
    assert doc["well_name"] == "SYN-ASM-01"
    assert doc["report_date"] == "2020-01-02"
    assert doc["synthetic"] is True

    page = _get(f"/api/v1/documents/{doc_id}/pages/1").json()
    title = [s for s in page["spans"] if s["text"] == "DAILY DRILLING REPORT"]
    assert title and all(0 <= v <= 1 for v in title[0]["bbox"])
    img = httpx.get(f"{API}{page['image_url']}", timeout=30)
    assert img.status_code == 200 and img.content.startswith(b"\x89PNG")
    original = httpx.get(f"{API}/api/v1/documents/{doc_id}/file", timeout=30)
    assert original.content == data

    again = httpx.post(
        f"{API}/api/v1/documents",
        files={"files": ("x.pdf", io.BytesIO(data), "application/pdf")},
        timeout=30,
    )
    assert again.json()[0] == {**again.json()[0], "document_id": doc_id, "duplicate": True}

    listed = _get("/api/v1/documents", well_id=doc["well_id"]).json()
    assert any(d["id"] == doc_id for d in listed["items"])


def test_rejects_unsupported_files() -> None:
    r = httpx.post(
        f"{API}/api/v1/documents", files={"files": ("a.txt", b"hello", "text/plain")}, timeout=30
    )
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "unsupported_file_type"
