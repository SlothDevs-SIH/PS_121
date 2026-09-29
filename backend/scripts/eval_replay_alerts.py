"""Replay the drilling well through the running stack and score the alerts it raises.

Starts a replay of the SYNTHETIC drilling well at ``--speed`` (default 60, the demo speed),
waits until every row is published and scored, then compares the alerts with the replay's
truth file (what was planted, when):

- per planted event: the first alert of that event type and its lead time (data minutes
  before the event starts; negative = after), and which sources joined it;
- alerts for event types that were not planted (false alerts, by type);
- alert latency: wall time from the triggering sample's publication to the stored alert
  (``detail.latency_ms``, recorded by the stream service), for created and fused alerts.

Needs the seeded stack with the stream service (``docker compose up``, ``seed``).

    cd backend && uv run python scripts/eval_replay_alerts.py --speed 60
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.risk import assets

API = os.environ.get("SMRITI_API_URL", "http://localhost:8000")
OUT_DIR = Path(__file__).resolve().parents[2] / "eval" / "results"


def _get(path: str, **params: Any) -> Any:
    r = httpx.get(f"{API}{path}", params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=float, default=60.0)
    args = ap.parse_args()

    well = _get("/api/v1/wells", status="drilling", limit=1)["items"][0]
    truth = json.loads(assets.get_object(assets.replay_truth_key(well["name"])))
    r = httpx.post(
        f"{API}/api/v1/replay", json={"well_id": well["id"], "speed": args.speed}, timeout=60
    )
    r.raise_for_status()
    sid = r.json()["id"]
    t_wall = time.monotonic()
    while True:
        cur = next(s for s in _get("/api/v1/replay") if s["id"] == sid)
        if cur["status"] in ("finished", "failed", "stopped"):
            break
        time.sleep(10)
    if cur["status"] != "finished":
        sys.exit(f"replay ended {cur['status']}: {cur['error']}")
    while True:  # scoring may trail publishing
        win = _get(f"/api/v1/wells/{well['id']}/realtime", minutes=24 * 60)
        last = datetime.fromisoformat(win["ts"][-1]) if win["ts"] else None
        if win["latest"] and last and datetime.fromisoformat(win["latest"]["ts"]) >= last:
            break
        time.sleep(5)
    time.sleep(5)
    wall_s = time.monotonic() - t_wall
    alerts = _get("/api/v1/alerts", session_id=sid, limit=500)["items"]

    def minutes_before(t_event: str, t_alert: str) -> float:
        return round(
            (datetime.fromisoformat(t_event) - datetime.fromisoformat(t_alert)).total_seconds()
            / 60,
            1,
        )

    planted_types = {p["event_type"] for p in truth["planted"]}
    per_event = []
    for p in truth["planted"]:
        same = sorted(
            (a for a in alerts if a["event_type"] == p["event_type"]), key=lambda a: a["t_data"]
        )
        first = same[0] if same else None
        joined = []
        if first:
            joined = [first["sources"][0]] + [
                {
                    "source": f["source"],
                    "minutes_before_event": minutes_before(p["t_start"], f["t_data"]),
                }
                for f in first["detail"].get("fused", [])
            ]
        per_event.append(
            {
                "event_type": p["event_type"],
                "t_start": p["t_start"],
                "md_at_start_m": p["md_at_start_m"],
                "alerted": first is not None,
                "first_alert_type": first["sources"][0] if first else None,
                "first_alert_minutes_before_event": (
                    minutes_before(p["t_start"], first["t_data"]) if first else None
                ),
                "sources": first["sources"] if first else [],
                "timeline": joined,
            }
        )
    latencies = [a["detail"]["latency_ms"] for a in alerts if "latency_ms" in a["detail"]]
    latencies += [
        f["latency_ms"] for a in alerts for f in a["detail"].get("fused", []) if "latency_ms" in f
    ]
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 (developer tool on PATH)
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    result = {
        "what": "End-to-end replay of the SYNTHETIC drilling well: alerts vs planted events",
        "measured_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "commit": commit or None,
        "well": well["name"],
        "speed": args.speed,
        "rows": cur["total_rows"],
        "data_hours": round(cur["total_rows"] * truth["dt_s"] / 3600, 2),
        "wall_seconds": round(wall_s, 1),
        "planted": per_event,
        "alerts": [
            {
                "t_data": a["t_data"],
                "event_type": a["event_type"],
                "alert_type": a["alert_type"],
                "sources": a["sources"],
                "severity": a["severity"],
                "score": a["score"],
                "score_kind": a["score_kind"],
                "evidence_items": len(a["evidence"]),
                "recommendations": len(a["recommendations"]),
            }
            for a in sorted(alerts, key=lambda a: a["t_data"])
        ],
        "false_alerts_by_type": {
            t: sum(1 for a in alerts if a["event_type"] == t)
            for t in sorted({a["event_type"] for a in alerts} - planted_types)
        },
        "latency_ms": {
            "n": len(latencies),
            "median": round(statistics.median(latencies), 1) if latencies else None,
            "max": round(max(latencies), 1) if latencies else None,
        },
        "notes": [
            "SYNTHETIC: the precursors were planted by our simulator; one scenario, one run. "
            "This shows the pipeline end to end, not detection skill on real wells.",
            "Lead time is in data minutes (the replay's clock), before the planted start.",
            "Latency is wall time from publishing the triggering sample to storing the alert "
            "(includes evidence and ledger lookups), at this replay speed.",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"replay_alerts_synthetic_{datetime.now(tz=UTC):%Y-%m-%d}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "alerts"}, indent=2))
    print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
