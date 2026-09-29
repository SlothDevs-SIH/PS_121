"""B4 behaviour against the running, seeded stack: replay → stream service → scoring →
alerts, over HTTP and both WebSockets (S12, S7b-d, S9).

The seed builds the real-time assets (classifiers, Déjà Vu library, the drilling well's
SYNTHETIC replay file with planted balling and losses). CI seeds a small field, so these
tests check invariants rather than fixed numbers: every alert carries evidence, similarity
is never labelled a probability, planted losses are alerted, the lifecycle rules hold.
"""

import json
import os
import threading
import time
from datetime import datetime
from typing import Any

import httpx
import pytest
from websockets.sync.client import connect

pytestmark = pytest.mark.integration

API = os.environ.get("SMRITI_API_URL", "http://localhost:8000")
WS = API.replace("http", "ws", 1)
SPEED = 1500.0  # data seconds per wall second: 5 h of data in ~12 s of publishing


def _req(method: str, path: str, status: int = 200, **kw: Any) -> Any:
    r = httpx.request(method, f"{API}{path}", timeout=60, **kw)
    assert r.status_code == status, r.text
    return r.json()


def _drilling_well() -> dict[str, Any]:
    wells = _req("GET", "/api/v1/wells", params={"status": "drilling", "limit": 10})["items"]
    assert wells, "the seed has one drilling well"
    return dict(wells[0])


@pytest.fixture(scope="module")
def replayed() -> dict[str, Any]:
    """Replay the drilling well once for the module, collecting both WebSockets' messages."""
    well = _drilling_well()
    wid = well["id"]
    assert _req("GET", "/api/v1/stream/status")["service_alive"]
    got: dict[str, list[Any]] = {"alerts": [], "live": []}
    stop = threading.Event()

    def listen(path: str, sink: list[Any]) -> None:
        with connect(f"{WS}{path}", open_timeout=10) as ws:
            while not stop.is_set():
                try:
                    sink.append(json.loads(ws.recv(timeout=0.5)))
                except TimeoutError:
                    continue

    threads = [
        threading.Thread(target=listen, args=(f"/ws/alerts?well_id={wid}", got["alerts"])),
        threading.Thread(target=listen, args=(f"/ws/wells/{wid}/live", got["live"])),
    ]
    for t in threads:
        t.start()
    time.sleep(1.0)  # both sockets read from "now"
    session = _req("POST", "/api/v1/replay", json={"well_id": wid, "speed": SPEED})
    assert session["status"] == "pending" and session["synthetic"]
    deadline = time.monotonic() + 420
    while time.monotonic() < deadline:
        cur = next(s for s in _req("GET", "/api/v1/replay") if s["id"] == session["id"])
        if cur["status"] in ("finished", "failed"):
            break
        time.sleep(2)
    assert cur["status"] == "finished", cur
    # Scoring may trail publishing: wait until the last sample has been scored.
    while time.monotonic() < deadline:
        win = _req("GET", f"/api/v1/wells/{wid}/realtime", params={"minutes": 24 * 60})
        if (
            win["latest"]
            and win["latest"]["ts"]
            and win["ts"]
            and (
                datetime.fromisoformat(win["latest"]["ts"]) >= datetime.fromisoformat(win["ts"][-1])
            )
        ):
            break
        time.sleep(2)
    time.sleep(2)
    stop.set()
    for t in threads:
        t.join(timeout=10)
    alerts = _req("GET", "/api/v1/alerts", params={"session_id": session["id"]})["items"]
    return {"well": well, "session": cur, "window": win, "alerts": alerts, "ws": got}


def test_every_row_is_stored_and_scored(replayed: dict[str, Any]) -> None:
    s, win = replayed["session"], replayed["window"]
    assert s["position"] == s["total_rows"] > 1000
    full = _req(
        "GET",
        f"/api/v1/wells/{s['well_id']}/realtime",
        params={"minutes": 24 * 60, "max_points": 5000},
    )
    assert len(full["ts"]) == s["total_rows"]  # every published row persisted, once
    assert set(win["channels"]) == set(win["units"]) and win["units"]["torque_knm"] == "kN.m"
    assert {"DRILLING", "IN_SLIPS"} <= {r for r in full["rig_state"] if r}
    assert win["thresholds"] and win["scores"], "classifier scores and thresholds are served"
    for probs in win["scores"].values():
        assert all(p is None or 0 <= p <= 1 for p in probs)


def test_planted_losses_are_alerted_with_evidence(replayed: dict[str, Any]) -> None:
    alerts = replayed["alerts"]
    assert alerts, "the replay raised no alert"
    loss = [a for a in alerts if a["event_type"] == "LOSS"]
    assert loss, [(a["alert_type"], a["event_type"]) for a in alerts]
    for a in alerts:
        assert a["evidence"], "no citation, no claim"
        assert a["synthetic"] is True
        assert a["status"] == "new"
        if a["alert_type"] == "FUSED":
            assert len(set(a["sources"])) >= 2
        kinds = {"ANOMALY_ML": "probability", "DEJA_VU": "similarity", "PHYSICS": "indicator",
                 "LOOKAHEAD": "prior"}  # fmt: skip
        if a["alert_type"] in kinds:
            assert a["score_kind"] == kinds[a["alert_type"]]
        for e in a["evidence"]:
            if e["kind"] == "stream":
                assert e["wellbore_id"] == replayed["session"]["wellbore_id"] and e["channels"]
            else:
                assert e["event_id"] and e["well_id"] != a["well_id"]  # never its own well
        for d in a["drivers"]:
            assert d["label"] and d["contribution"] > 0
        assert a["detail"]["latency_ms"] >= 0


def test_budget_and_dedupe_hold(replayed: dict[str, Any]) -> None:
    alerts = replayed["alerts"]
    non_critical = [a for a in alerts if not a["budget_exempt"]]
    assert len(non_critical) <= 6  # a 5-6 h replay sits inside one 12-h budget window
    seen: dict[str, list[float]] = {}
    for a in alerts:
        if a["tvdss_m"] is None:
            continue
        for other in seen.get(a["event_type"], []):
            assert abs(other - a["tvdss_m"]) > 30 or a["alert_type"] == "LOOKAHEAD"
        seen.setdefault(a["event_type"], []).append(a["tvdss_m"])


def test_websockets_pushed_frames_and_alerts(replayed: dict[str, Any]) -> None:
    live = replayed["ws"]["live"]
    assert live[0]["type"] == "hello" and live[0]["well_id"] == replayed["well"]["id"]
    frames = [m["frame"] for m in live if m["type"] == "frame"]
    assert len(frames) >= 5
    assert {"values", "rig_state", "latest_scores"} <= set(frames[-1])
    assert any(m["type"] == "status" for m in live)
    pushed = {m["alert"]["id"] for m in replayed["ws"]["alerts"] if m["type"] == "alert"}
    assert pushed == {a["id"] for a in replayed["alerts"]}


def test_alert_lifecycle(replayed: dict[str, Any]) -> None:
    alerts = replayed["alerts"]
    first = alerts[0]
    acked = _req("POST", f"/api/v1/alerts/{first['id']}/ack")
    assert acked["status"] == "ack" and acked["acked_by"] == "dev" and acked["acked_at"]
    _req("POST", f"/api/v1/alerts/{first['id']}/ack", status=409)
    fb = _req(
        "POST",
        f"/api/v1/alerts/{first['id']}/feedback",
        status=201,
        json={"verdict": "useful", "comment": "caught it"},
    )
    assert fb["verdict"] == "useful"
    assert _req("GET", f"/api/v1/alerts/{first['id']}")["feedback"][-1]["id"] == fb["id"]
    dismissed = _req(
        "POST", f"/api/v1/alerts/{first['id']}/dismiss", json={"reason": "handled on the rig"}
    )
    assert dismissed["status"] == "dismissed"
    _req("POST", f"/api/v1/alerts/{first['id']}/dismiss", status=409, json={"reason": "again"})
    page = _req("GET", "/api/v1/alerts", params={"well_id": first["well_id"], "status": "new"})
    assert first["id"] not in {a["id"] for a in page["items"]}
    assert page["counts"].get("dismissed", 0) >= 1
    _req("GET", "/api/v1/alerts/999999999", status=404)


def test_replay_control_rules(replayed: dict[str, Any]) -> None:
    wid = replayed["well"]["id"]
    # The module's replay has finished: it cannot be paused or stopped any more.
    _req("POST", "/api/v1/replay", status=409, json={"well_id": wid, "action": "pause"})
    wells = _req("GET", "/api/v1/wells", params={"status": "completed", "limit": 1})["items"]
    r = _req("POST", "/api/v1/replay", status=404, json={"well_id": wells[0]["id"]})
    assert "replay file" in r["error"]["message"]
    _req("POST", "/api/v1/replay", status=404, json={"well_id": 999999})
