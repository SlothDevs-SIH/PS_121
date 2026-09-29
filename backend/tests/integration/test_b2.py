"""B2 behaviour against the running, seeded stack (runs in GitHub CI after `seed --wait`):
extraction with evidence, events, review queue, hybrid search, correlation, subsurface
proximity and trajectory. Checks use independent paths where they can (evidence spans
against the page endpoint, entry-point distances against at-depth positions)."""

import io
import math
import os
import time
import uuid
from typing import Any

import httpx
import pytest
from fpdf import FPDF

pytestmark = pytest.mark.integration

API = os.environ.get("SMRITI_API_URL", "http://localhost:8000")


def _get(path: str, status: int = 200, **params: Any) -> Any:
    r = httpx.get(f"{API}{path}", params=params, timeout=60)
    assert r.status_code == status, r.text
    return r.json()


def _send(method: str, path: str, body: Any, status: int) -> Any:
    r = httpx.request(method, f"{API}{path}", json=body, timeout=60)
    assert r.status_code == status, r.text
    return r.json()


def _events(**params: Any) -> list[dict[str, Any]]:
    return list(_get("/api/v1/events", limit=500, **params)["items"])


def _span_ids(document_id: int, page_no: int) -> set[int]:
    page = _get(f"/api/v1/documents/{document_id}/pages/{page_no}")
    return {s["id"] for s in page["spans"]}


# ─── Extraction and events ────────────────────────────────────────────────────────────────


def test_extracted_events_cite_spans_on_their_pages() -> None:
    events = _events()
    assert events, "seeding should have extracted events"
    for ev in events[:15]:
        assert ev["source"] == "rules" or ev["source"] == "manual"
        assert 0 <= ev["confidence"] <= 1
        if ev["source"] == "rules":
            assert ev["evidence"], f"event {ev['id']} has no evidence"
        for ref in ev["evidence"]:
            assert set(ref["span_ids"]) <= _span_ids(ref["document_id"], ref["page_no"])
    detail = _get(f"/api/v1/events/{events[0]['id']}")
    assert set(detail["params"]) >= {"loss_rate_m3_h", "overpull_kn"}  # every key present
    if detail["source"] == "rules":
        assert detail["lesson_card"]["generated_by"].startswith("template:")
    for m in detail["mitigations"]:
        for ref in m["evidence"]:
            assert set(ref["span_ids"]) <= _span_ids(ref["document_id"], ref["page_no"])
    assert [m["seq"] for m in detail["mitigations"]] == sorted(
        m["seq"] for m in detail["mitigations"]
    )


def test_event_cursor_pages_cover_the_list_once_in_order() -> None:
    everything = _events()
    seen: list[int] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"limit": 7}
        if cursor:
            params["cursor"] = cursor
        page = _get("/api/v1/events", **params)
        seen += [e["id"] for e in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == [e["id"] for e in everything]
    keys = [
        (e["well_name"], e["md_m"] if e["md_m"] is not None else 1e9, e["id"]) for e in everything
    ]
    assert keys == sorted(keys)
    _get("/api/v1/events", status=422, cursor="not-a-cursor")


def test_event_filters() -> None:
    losses = _events(event_type="LOSS")
    assert all(e["event_type"] == "LOSS" for e in losses)
    by_fm = _events(formation="TPM")  # a synonym of Tipam Sandstone
    assert all(e["formation"] == "Tipam Sandstone" for e in by_fm)
    _get("/api/v1/events", status=422, formation="Atlantis")
    deep = _events(tvdss_from_m=2500)
    assert all(e["tvdss_m"] is not None and e["tvdss_m"] >= 2500 for e in deep)
    sure = _events(min_confidence=0.9)
    assert all(e["confidence"] >= 0.9 for e in sure)


def test_timeline_counts_and_npt_lines() -> None:
    wid = _events()[0]["well_id"]
    tl = _get(f"/api/v1/wells/{wid}/events/timeline")
    assert sum(tl["counts_by_type"].values()) == len(tl["events"])
    ids = {e["id"] for e in tl["events"]}
    for op in tl["npt_operations"]:
        assert op["is_npt"] and (op["event_id"] is None or op["event_id"] in ids)


def test_manual_event_verify_and_reject() -> None:
    source = next(e for e in _events() if e["evidence"] and e["md_m"])
    ref = source["evidence"][0]
    body = {
        "well_id": source["well_id"],
        "event_type": "TIGHT",
        "md_m": source["md_m"],
        "description": f"integration test {uuid.uuid4().hex[:8]}",
        "mitigations": [{"action_code": "REAM", "outcome": "success"}],
        "evidence": [
            {
                "document_id": ref["document_id"],
                "page_no": ref["page_no"],
                "span_ids": ref["span_ids"][:1],
            }
        ],
    }
    other_page_span = max(_span_ids(ref["document_id"], ref["page_no"])) + 10_000_000
    bad = {**body, "evidence": [{**body["evidence"][0], "span_ids": [other_page_span]}]}
    _send("POST", "/api/v1/events", bad, 422)

    ev = _send("POST", "/api/v1/events", body, 201)
    assert (ev["source"], ev["verified"], ev["confidence"]) == ("manual", False, 1.0)
    assert ev["tvdss_m"] == pytest.approx(source["tvdss_m"], abs=0.2)  # derived from md_m
    assert ev["formation"] == source["formation"]
    assert ev["lesson_card"] is not None

    ok = _send("PATCH", f"/api/v1/events/{ev['id']}/verify", {"verified": True}, 200)
    assert ok["verified"] and ok["verified_by"] and ok["mitigations"][0]["verified"]
    gone = _send(
        "PATCH", f"/api/v1/events/{ev['id']}/verify", {"verified": False, "status": "rejected"}, 200
    )
    assert gone["status"] == "rejected" and not gone["verified"]
    assert ev["id"] not in {e["id"] for e in _events(well_id=source["well_id"])}
    assert _get(f"/api/v1/events/{ev['id']}")["status"] == "rejected"


# ─── Review queue ──────────────────────────────────────────────────────────────────────────


def _low_confidence_ddr() -> bytes:
    """A DDR whose NPT row names no problem and no depth unit in the text: extraction can
    only use the code and the time-log column, so the event lands in the review queue."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in (
        "DAILY DRILLING REPORT",
        "SYNTHETIC DATA - NOT OIL INDIA DATA",
        "Well: SYN-ASM-01    Rig: Rig SYN-1    Report No: 98    Date: 2020-03-04",
        f"Depth at 24:00: 2,000 m    Hole size: 12-1/4 in    Nonce {uuid.uuid4().hex[:12]}",
        "TIME LOG",
        "From  To  Hrs  Depth (m)  Code  Operation",
        "00:00  06:00  6.0  1995  DRL  Drilled ahead",
        "06:00  09:00  3.0  1995  NPT-LOSS  Operations suspended",
        "09:00  24:00  15.0  1995  CIRC  Circulated",
        "REMARKS",
        "See time log.",
    ):
        pdf.cell(0, 7, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def _wait_extracted(doc_id: int) -> dict[str, Any]:
    deadline = time.monotonic() + 120
    while True:
        doc = _get(f"/api/v1/documents/{doc_id}")
        if (
            doc["extract_status"] in ("done", "failed", "skipped")
            and doc["index_status"] != "running"
        ):
            return dict(doc)
        assert time.monotonic() < deadline, f"document {doc_id} not extracted: {doc}"
        time.sleep(1)


def test_review_queue_accept_then_conflict() -> None:
    files = {"files": ("it_low_conf.pdf", io.BytesIO(_low_confidence_ddr()), "application/pdf")}
    r = httpx.post(f"{API}/api/v1/documents", files=files, timeout=30)
    assert r.status_code == 202, r.text
    doc = _wait_extracted(r.json()[0]["document_id"])
    assert doc["extract_status"] == "done", doc
    assert doc["event_count"] >= 1

    page = _get("/api/v1/review-queue", document_id=doc["id"])
    items = [i for i in page["items"] if i["kind"] == "event"]
    assert items, page
    item = items[0]
    assert item["confidence"] < 0.75 and "NPT code" in item["reason"]
    assert item["proposed"]["event_type"] == "LOSS"
    assert set(item["span_ids"]) <= _span_ids(doc["id"], item["page_no"])
    assert set(page["status_counts"]) == {"pending", "accepted", "corrected", "rejected"}

    wrong_kind = {"action": "correct", "fields": {"shoe_md_m": 5}}  # a casing field
    _send("POST", f"/api/v1/review-queue/{item['id']}", wrong_kind, 422)
    fix = {"action": "correct", "fields": {"md_m": 1996}}
    decided = _send("POST", f"/api/v1/review-queue/{item['id']}", fix, 200)
    assert decided["status"] == "corrected" and decided["decided_by"]
    ev = _get(f"/api/v1/events/{item['target_id']}")
    assert ev["verified"] and ev["md_m"] == 1996
    again = httpx.post(
        f"{API}/api/v1/review-queue/{item['id']}", json={"action": "accept"}, timeout=30
    )
    assert again.status_code == 409 and again.json()["error"]["code"] == "conflict"


# ─── Search ────────────────────────────────────────────────────────────────────────────────


def test_hybrid_search_cites_passages_and_says_when_nothing_is_found() -> None:
    res = _get("/api/v1/search", q="stuck pipe overpull", limit=5)
    assert res["passages"] and not res["no_record_found"]
    assert res["embedding_provider"].startswith(("hash:", "ollama:"))
    for p in res["passages"]:
        assert p["lexical_rank"] or p["dense_rank"]
        for a, b in p["highlights"]:
            assert 0 <= a < b <= len(p["snippet"])
    scores = [p["score"] for p in res["passages"]]
    assert scores == sorted(scores, reverse=True)
    for card in res["lessons"]:
        assert card["evidence"] and card["problem"]

    none = _get("/api/v1/search", q="quarterly football revenue")
    assert none["no_record_found"] and none["passages"] == [] and none["lessons"] == []

    only = _get("/api/v1/search", q="losses", event_type="LOSS", doc_type="DDR")
    assert all(p["doc_type"] == "DDR" for p in only["passages"])
    assert all(c["event_type"] == "LOSS" for c in only["lessons"])


# ─── Correlation ───────────────────────────────────────────────────────────────────────────


def _wells_with_tops(n: int) -> list[int]:
    out = []
    for w in _get("/api/v1/wells", limit=500)["items"]:
        if w["status"] != "planned" and _get(f"/api/v1/wells/{w['id']}")["formation_tops"]:
            out.append(w["id"])
        if len(out) == n:
            break
    return out


def test_correlation_alignments() -> None:
    wells = _wells_with_tops(3)
    tv = _get("/api/v1/correlation", wells=wells)
    assert [w["well_id"] for w in tv["wells"]] == wells
    for w in tv["wells"]:
        for f in w["tracks"]["formations"]:
            assert f["top"] == pytest.approx(f["top_tvdss_m"], abs=0.01)
            assert tv["depth_axis"]["min"] <= f["top"] <= tv["depth_axis"]["max"]

    flat = _get("/api/v1/correlation", wells=wells, align="FLATTEN_ON_TOP", top="Girujan Clay")
    for w in flat["wells"]:
        if not w["fallback_to_tvdss"]:
            (fm,) = [f for f in w["tracks"]["formations"] if f["name"] == "Girujan Clay"]
            assert fm["top"] == 0
        else:
            assert w["reason"]

    rel = _get("/api/v1/correlation", wells=wells, align="FORMATION_RELATIVE")
    assert rel["depth_axis"]["unit"] == "formation"
    for w in rel["wells"]:
        for f in w["tracks"]["formations"]:
            assert float(f["top"]).is_integer()
        for e in w["tracks"]["events"]:
            if e["relative_position"] is not None:
                assert e["relative_position"] >= 0

    _get("/api/v1/correlation", status=404, wells=[wells[0], 999999])


def test_formation_stats() -> None:
    wells = _wells_with_tops(4)
    st = _get("/api/v1/correlation/formation-stats", wells=wells)
    assert st["wells"] == wells
    orders = [r["strat_order"] for r in st["rows"]]
    assert orders == sorted(orders)
    for r in st["rows"]:
        assert r["wells_penetrating"] <= len(wells)
        assert all(n <= len(wells) for n in r["wells_with_event_by_type"].values())
    around = _get("/api/v1/correlation/formation-stats", well_id=wells[0], radius_km=5)
    assert around["wells"][0] == wells[0]


# ─── Subsurface proximity and trajectory ───────────────────────────────────────────────────


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def test_at_formation_matches_independent_positions_and_bounds_closest_approach() -> None:
    wid = _wells_with_tops(1)[0]
    fm = _get(f"/api/v1/wells/{wid}")["formation_tops"][2]["formation"]
    at = _get(f"/api/v1/wells/{wid}/offsets", mode="AT_FORMATION", formation=fm, radius_km=20)
    assert at["distance_label"].endswith(fm) and at["subject_entry_md_m"] is not None
    me = _get(f"/api/v1/wells/{wid}/trajectory/at-depth", md_m=at["subject_entry_md_m"])
    close = _get(f"/api/v1/wells/{wid}/offsets", mode="CLOSEST_APPROACH", radius_km=20)
    closest = {o["well_id"]: o["distance_m"] for o in close["offsets"]}
    for o in at["offsets"][:5]:
        other = _get(f"/api/v1/wells/{o['well_id']}/trajectory/at-depth", md_m=o["entry_md_m"])
        horizontal = _haversine_m(me["lat"], me["lon"], other["lat"], other["lon"])
        expected = math.hypot(horizontal, other["tvdss_m"] - me["tvdss_m"])
        assert o["distance_m"] == pytest.approx(expected, rel=0.01, abs=1.0)
        # The entry points lie on both paths, so the paths come at least that close.
        if o["well_id"] in closest:
            assert closest[o["well_id"]] <= o["distance_m"] + 1.0
    _get(f"/api/v1/wells/{wid}/offsets", status=422, mode="AT_FORMATION")
    _get(f"/api/v1/wells/{wid}/offsets", status=422, mode="AT_FORMATION", formation="Atlantis")


def test_trajectory_at_depth_and_idempotent_survey_upload() -> None:
    wid = _wells_with_tops(1)[0]
    traj = _get(f"/api/v1/wells/{wid}/trajectory")
    st = traj["stations"][len(traj["stations"]) // 2]
    at = _get(f"/api/v1/wells/{wid}/trajectory/at-depth", md_m=st["md_m"])
    assert at["tvd_m"] == pytest.approx(st["tvd_m"], abs=0.01)
    assert at["north_m"] == pytest.approx(st["north_m"], abs=0.01)
    _get(f"/api/v1/wells/{wid}/trajectory/at-depth", status=422, md_m=14999)

    before = _events(well_id=wid)
    body = {
        "stations": [
            {"md_m": s["md_m"], "inc_deg": s["inc_deg"], "azi_deg": s["azi_deg"] % 360}
            for s in traj["stations"]
        ]
    }
    again = _send("POST", f"/api/v1/wells/{wid}/trajectory", body, 200)
    assert not again["assumed"]
    for a, b in zip(traj["stations"], again["stations"], strict=True):
        assert b["tvd_m"] == pytest.approx(a["tvd_m"], abs=1e-6)
    after = {e["id"]: e for e in _events(well_id=wid)}
    for e in before:
        if e["tvdss_m"] is not None:
            assert after[e["id"]]["tvdss_m"] == pytest.approx(e["tvdss_m"], abs=0.2)


def test_well_360_enrichment() -> None:
    wid = _events()[0]["well_id"]
    d = _get(f"/api/v1/wells/{wid}")
    assert sum(d["event_counts"].values()) >= len(d["recent_events"]) > 0
    assert d["documents"]["total"] == sum(d["documents"]["by_doc_type"].values())
    for c in d["casing"]:
        for ref in c["evidence"]:
            assert set(ref["span_ids"]) <= _span_ids(ref["document_id"], ref["page_no"])
    for card in d["lessons"]:
        assert card["well_id"] == wid and card["evidence"]
