"""B3 behaviour against the running, seeded stack: the Mitigation Effectiveness Ledger (S8),
offset prior risk (S7a) and the cementing checklist (S7c).

GitHub CI seeds a small field (12 wells, 30 documents), so these tests check invariants and
recompute every number through an independent path (ledger counts from the events API,
risk posteriors from the offsets listed, base rates from well tops and events) instead of
expecting fixed values. Recovery of the planted ranking and the Brier-score comparison run on
the full field: scripts/eval_ledger.py and scripts/eval_risk_prior.py.
"""

import itertools
import math
import os
from collections import Counter, defaultdict
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.integration

API = os.environ.get("SMRITI_API_URL", "http://localhost:8000")
MIN_BASE_RATE = 0.01  # app.risk.core.MIN_BASE_RATE, restated so the test is independent


def _get(path: str, status: int = 200, **params: Any) -> Any:
    r = httpx.get(f"{API}{path}", params=params, timeout=60)
    assert r.status_code == status, r.text
    return r.json()


def _events(**params: Any) -> list[dict[str, Any]]:
    return list(_get("/api/v1/events", limit=500, **params)["items"])


def _wells() -> list[dict[str, Any]]:
    return list(_get("/api/v1/wells", limit=500)["items"])


def _drilled_with_tops() -> list[tuple[int, list[dict[str, Any]]]]:
    out = []
    for w in _wells():
        if w["status"] != "planned":
            tops = _get(f"/api/v1/wells/{w['id']}")["formation_tops"]
            if tops:
                out.append((w["id"], tops))
    return out


def _surface_offsets(wid: int) -> dict[int, dict[str, Any]]:
    return {o["well_id"]: o for o in _get(f"/api/v1/wells/{wid}/offsets", radius_km=10)["offsets"]}


# ─── Ledger ───────────────────────────────────────────────────────────────────────────────


def test_ledger_recounts_from_the_events_api() -> None:
    for et in ("LOSS", "STUCK", "TIGHT", "BALLING"):
        body = _get("/api/v1/ledger", event_type=et)
        events = _events(event_type=et)
        recorded: Counter[tuple[str, str]] = Counter()
        for ev in events:
            for m in _get(f"/api/v1/events/{ev['id']}")["mitigations"]:
                recorded[(m["action_code"], m["outcome"])] += 1
        entries = {e["action_code"]: e for e in body["ranked"] + body["insufficient"]}
        assert set(entries) == {code for code, _ in recorded}
        for code, e in entries.items():
            # A recurrence can only move a recorded success to partial; nothing else moves.
            assert (
                e["successes"] + e["partial"]
                == recorded[code, "success"] + recorded[code, "partial"]
            )
            assert e["successes"] <= recorded[code, "success"]
            assert e["failures"] == recorded[code, "fail"]
            assert e["unknown"] == recorded[code, "unknown"]
        assert body["scope"]["events"] == len(events)
        assert body["scope"]["wells"] == len({ev["well_id"] for ev in events})
        assert body["scope"]["mitigations"] == sum(recorded.values())


def test_ledger_rates_ranking_and_cases() -> None:
    body = _get("/api/v1/ledger", event_type="LOSS")
    assert body["synthetic"] is True
    assert body["caveat"].startswith("Observational") and "not proven" in body["caveat"]
    assert "unknown outcomes are excluded" in body["outcome_rule"]
    min_n = body["min_n"]
    assert all(e["n"] >= min_n for e in body["ranked"])
    assert all(e["n"] < min_n for e in body["insufficient"])
    means = [e["posterior_mean"] for e in body["ranked"]]
    assert means == sorted(means, reverse=True)
    for e in body["ranked"] + body["insufficient"]:
        assert e["successes"] + e["partial"] + e["failures"] == e["n"]
        if e["n"]:
            assert e["posterior_mean"] == pytest.approx((1 + e["successes"]) / (2 + e["n"]), 1e-3)
            assert e["ci90_low"] <= e["posterior_mean"] <= e["ci90_high"]
            assert e["success_rate"] == pytest.approx(e["successes"] / e["n"], abs=1e-4)
        assert sum(s["n"] for s in e["by_severity"]) == e["n"]
        for c in e["cases"]:
            expected = "partial" if c["recorded_outcome"] == "success" and c["recurred"] else None
            assert c["outcome"] == (expected or c["recorded_outcome"])
            assert c["evidence"], f"case {c['mitigation_id']} has no evidence"
            ref = c["evidence"][0]
            page = _get(f"/api/v1/documents/{ref['document_id']}/pages/{ref['page_no']}")
            assert set(ref["span_ids"]) <= {s["id"] for s in page["spans"]}

    everything = _get("/api/v1/ledger", event_type="LOSS", min_n=1)
    assert not [e for e in everything["insufficient"] if e["n"] >= 1]


def test_ledger_scopes() -> None:
    full = _get("/api/v1/ledger", event_type="LOSS")
    cases = [c for e in full["ranked"] + full["insufficient"] for c in e["cases"]]
    if not cases:
        pytest.skip("no LOSS mitigations in this seed")
    high = _get("/api/v1/ledger", event_type="LOSS", severity="high")
    assert all(c["severity"] == "high" for e in high["ranked"] for c in e["cases"])
    fm = next(c["formation"] for c in cases if c["formation"])
    scoped = _get("/api/v1/ledger", event_type="LOSS", formation=fm)
    assert scoped["formation"] == fm
    assert all(
        c["formation"] == fm for e in scoped["ranked"] + scoped["insufficient"] for c in e["cases"]
    )
    wid = cases[0]["well_id"]
    near = _get("/api/v1/ledger", event_type="LOSS", well_id=wid, radius_km=5)
    only = _get("/api/v1/ledger", event_type="LOSS", well_id=wid)
    assert only["scope"]["wells"] == 1 <= near["scope"]["wells"] <= full["scope"]["wells"]
    _get("/api/v1/ledger", 422, event_type="LOSS", radius_km=5)
    _get("/api/v1/ledger", 404, event_type="LOSS", well_id=999_999)


# ─── Offset prior risk ────────────────────────────────────────────────────────────────────


def test_risk_profile_recomputes_from_its_offsets_and_excludes_the_subject() -> None:
    drilled = _drilled_with_tops()
    wid = drilled[0][0]
    prof = _get(f"/api/v1/wells/{wid}/risk-profile")
    assert prof["mode"] == "AT_FORMATION" and prof["synthetic"] is True
    assert "never used" in prof["method"]
    surface = _surface_offsets(wid)
    by_type_well_fm: dict[tuple[str, int, str | None], set[int]] = defaultdict(set)
    for ev in _events():
        by_type_well_fm[ev["event_type"], ev["well_id"], ev["formation"]].add(ev["id"])

    sigma_m = prof["sigma_km"] * 1000
    assert prof["intervals"], "a drilled well with tops has intervals"
    for iv in prof["intervals"]:
        for o in iv["offsets"]:
            assert o["well_id"] != wid, "the subject is never its own offset"
            assert o["well_id"] in surface and surface[o["well_id"]]["status"] != "planned"
            w = math.exp(-(o["distance_m"] ** 2) / (2 * sigma_m**2)) * o["similarity"]
            assert o["weight"] == pytest.approx(w, abs=1e-5)
            for t, ids in o["events"].items():
                assert set(ids) == by_type_well_fm[t, o["well_id"], iv["formation"]]
        probs = [r["probability"] for r in iv["risks"]]
        assert probs == sorted(probs, reverse=True)
        for r in iv["risks"]:
            y = [r["event_type"] in o["events"] for o in iv["offsets"]]
            weights = [o["weight"] for o in iv["offsets"]]
            p0 = min(max(r["base_rate"], MIN_BASE_RATE), 1 - MIN_BASE_RATE)
            a, b = 2 * p0, 2 * (1 - p0)
            hits = sum(wi for wi, yi in zip(weights, y, strict=True) if yi)
            assert r["probability"] == pytest.approx((hits + a) / (sum(weights) + a + b), abs=5e-4)
            assert r["ci90_low"] <= r["probability"] <= r["ci90_high"]
            assert r["offsets_with_event"] == sum(y)
            assert r["offsets_total"] == len(iv["offsets"])
            if weights:
                n_eff = sum(weights) ** 2 / sum(x * x for x in weights)
                assert r["n_eff"] == pytest.approx(n_eff, abs=0.01)


def test_base_rates_exclude_the_subject_well() -> None:
    drilled = _drilled_with_tops()
    wid = drilled[0][0]
    pairs = {(w, t["formation"]) for w, tops in drilled if w != wid for t in tops}
    hits: dict[str, set[tuple[int, str]]] = defaultdict(set)
    for ev in _events():
        if (ev["well_id"], ev["formation"]) in pairs:
            hits[ev["event_type"]].add((ev["well_id"], ev["formation"]))
    prof = _get(f"/api/v1/wells/{wid}/risk-profile")
    for iv in prof["intervals"]:
        for r in iv["risks"]:
            expected = len(hits[r["event_type"]]) / len(pairs)
            assert r["base_rate"] == pytest.approx(expected, abs=1e-4)


def test_risk_profile_modes_and_planned_well() -> None:
    wid, tops = _drilled_with_tops()[0]
    surf = _get(f"/api/v1/wells/{wid}/risk-profile", mode="SURFACE", event_type=["LOSS", "KICK"])
    surface = _surface_offsets(wid)
    for iv in surf["intervals"]:
        assert {r["event_type"] for r in iv["risks"]} == {"LOSS", "KICK"}
        for o in iv["offsets"]:
            assert o["distance_kind"] == "surface"
            assert o["distance_m"] == pytest.approx(surface[o["well_id"]]["distance_m"], abs=0.1)
    # AT_FORMATION distances agree with the at-formation offsets endpoint.
    fm = tops[len(tops) // 2]["formation"]
    at = _get(f"/api/v1/wells/{wid}/offsets", mode="AT_FORMATION", formation=fm, radius_km=10)
    entry = {o["well_id"]: o["distance_m"] for o in at["offsets"]}
    prof = _get(f"/api/v1/wells/{wid}/risk-profile")
    iv = next(i for i in prof["intervals"] if i["formation"] == fm)
    for o in iv["offsets"]:
        if o["distance_kind"] == "at_formation":
            assert o["distance_m"] == pytest.approx(entry[o["well_id"]], abs=1.0)

    planned = next(w for w in _wells() if w["status"] == "planned")
    plan = _get(f"/api/v1/wells/{planned['id']}/risk-profile")
    assert plan["status"] == "planned" and plan["intervals"]
    assert all(o["well_id"] != planned["id"] for i in plan["intervals"] for o in i["offsets"])
    _get("/api/v1/wells/999999/risk-profile", 404)


# ─── Cementing checklist ──────────────────────────────────────────────────────────────────


def test_cementing_check_reads_offsets_in_the_shoe_formation() -> None:
    wid, tops = next((w, t) for w, t in _drilled_with_tops() if len(t) >= 4)
    fm = tops[3]
    shoe = fm["top_md_m"] + 5
    heavy = _get(f"/api/v1/wells/{wid}/cementing-check", shoe_md_m=shoe, slurry_density_sg=2.5)
    light = _get(f"/api/v1/wells/{wid}/cementing-check", shoe_md_m=shoe, slurry_density_sg=1.0)
    assert heavy["formation"] == light["formation"] == fm["formation"]
    loss_mw = []
    for eid in heavy["evidence_event_ids"]:
        ev = _get(f"/api/v1/events/{eid}")
        assert ev["well_id"] != wid and ev["formation"] == fm["formation"]
        assert ev["event_type"] in ("LOSS", "CEMENT")
        if ev["event_type"] == "LOSS":
            loss_mw.append(round(ev["mw_sg"], 3))
    assert sorted(loss_mw) == heavy["offset_loss_mw_sg"]
    if heavy["offset_loss_mw_sg"]:
        assert any("≥ lowest offset loss mud weight" in f for f in heavy["flags"])
        assert heavy["level"] in ("medium", "high")
    assert not any("≥ lowest offset loss mud weight" in f for f in light["flags"])

    above = _get(f"/api/v1/wells/{wid}/cementing-check", shoe_md_m=1, slurry_density_sg=1.5)
    assert above["formation"] is None and above["level"] == "low" and above["flags"] == []


def test_meta_reports_b3_built() -> None:
    meta = _get("/api/v1/meta")
    assert int(meta["backend_phase"].removeprefix("B")) >= 3  # B3 or a later phase
    status = {c["key"]: c["status"] for c in meta["components"]}
    assert status["risk_prior"] == status["physics"] == status["ledger"] == "built"


def test_depth_slices_tile_each_formation_and_never_exceed_it() -> None:
    """Part 7 (V-B20): bin_m splits each formation into formation-relative slices. They
    tile the formation, and no slice can have more offsets with an event than the
    formation as a whole (an offset's event lands in exactly one slice)."""
    wells = _get("/api/v1/wells", limit=500)["items"]
    wid = next(w["id"] for w in wells if w["status"] == "completed")
    plain = _get(f"/api/v1/wells/{wid}/risk-profile")
    sliced = _get(f"/api/v1/wells/{wid}/risk-profile", bin_m=100)
    assert all(iv["bins"] == [] for iv in plain["intervals"])
    assert [iv["risks"] for iv in sliced["intervals"]] == [iv["risks"] for iv in plain["intervals"]]
    checked = 0
    for iv in sliced["intervals"]:
        bins = iv["bins"]
        if not bins:
            continue
        checked += 1
        assert bins[0]["top_tvdss_m"] == pytest.approx(iv["top_tvdss_m"], abs=0.2)
        assert bins[-1]["base_tvdss_m"] == pytest.approx(iv["base_tvdss_m"], abs=0.2)
        for a, b in itertools.pairwise(bins):
            assert a["base_tvdss_m"] == pytest.approx(b["top_tvdss_m"], abs=0.2)
        assert all(b["base_tvdss_m"] - b["top_tvdss_m"] <= 100.5 for b in bins)
        whole = {r["event_type"]: r["offsets_with_event"] for r in iv["risks"]}
        for b in bins:
            for r in b["risks"]:
                assert r["offsets_with_event"] <= whole[r["event_type"]]
    assert checked > 0
    _get(f"/api/v1/wells/{wid}/risk-profile", status=422, bin_m=5)
