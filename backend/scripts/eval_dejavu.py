"""Score S7d Déjà Vu on the SYNTHETIC data (no database needed).

Library: the 90 min before every real-time event of the seeded field's wells (1-40), as the
seed builds it. Queries come from wells the library never saw (training field, 61+):

- event queries: the last 30 min before each event, and the 30 min ending 15 min earlier;
- precursor-free queries: normal drilling windows from another seed than the one tau is
  calibrated on, so the false-match rate is measured out of sample.

Reported: precision@1 (does the best match have the query's event type?) against a random
pick weighted by the library's type mix and a depth-only nearest neighbour; alert recall
(best similarity ≥ 0.8) and alert precision (share of those alerts with the right type);
false-match rate (precursor-free windows reaching 0.8); per-type rows; query latency.

    cd backend && uv run python scripts/eval_dejavu.py
"""

import json
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from app.risk import assets
from app.risk import dejavu as dv
from app.risk import realtime_model as rm
from app.synthetic import realtime as rt

OUT_DIR = Path(__file__).resolve().parents[2] / "eval" / "results"
CALIBRATION_WELLS = 40
LEAD_STEPS = {"at_event": 0, "15_min_before": 90}


def main() -> None:
    lib_eps = [e for e in rm.episodes_for(40, 1) if e.planted]
    library = [assets.signature_of(ep, i, well_id=i) for i, ep in enumerate(lib_eps)]
    lib_depth = np.array([float(ep.data["bit_depth_m"][rt.PRE_STEPS]) for ep in lib_eps])
    mix = Counter(s.event_type for s in library)

    calib = [
        e
        for e in rm.episodes_for(CALIBRATION_WELLS, rm.TRAINING_WELLS_FROM, seed=1)
        if not e.planted
    ]
    cal_d: list[float] = []
    for ep in calib:
        for end in assets.CALIBRATION_ENDS:
            q, share = assets.query_window(ep.data, end)
            found = dv.search(q, library, 1.0, share, ep.hole_size_in, top=1)
            if found:
                cal_d.append(found[0].distance)
    tau = dv.calibrate_tau(cal_d)

    test = rm.episodes_for(40, rm.TRAINING_WELLS_FROM, seed=2)
    events = [e for e in test if e.planted and e.planted[0].event_type in mix]
    normals = [e for e in test if not e.planted]

    latencies: list[float] = []

    def best(ep: rt.Episode, end: int) -> dv.Match | None:
        q, share = assets.query_window(ep.data, end)
        t = time.perf_counter()
        m = dv.search(q, library, tau, share, ep.hole_size_in, top=1)
        latencies.append((time.perf_counter() - t) * 1000)
        return m[0] if m else None

    by_lead: dict[str, Any] = {}
    for name, lead in LEAD_STEPS.items():
        per: dict[str, Counter[str]] = defaultdict(Counter)
        for ep in events:
            et = ep.planted[0].event_type
            m = best(ep, rt.PRE_STEPS - lead)
            c = per[et]
            c["n"] += 1
            if m is None:
                continue
            c["top1"] += m.signature.event_type == et
            if m.similarity >= dv.ALERT_SIMILARITY:
                c["alerts"] += 1
                c["alerts_right"] += m.signature.event_type == et
            depth = float(ep.data["bit_depth_m"][rt.PRE_STEPS])
            c["depth_top1"] += library[int(np.argmin(np.abs(lib_depth - depth)))].event_type == et
        tot: Counter[str] = sum(per.values(), Counter())
        by_lead[name] = {
            "queries": tot["n"],
            "precision_at_1": round(tot["top1"] / tot["n"], 3),
            "baseline_random_by_type_mix": round(
                sum(per[t]["n"] * mix[t] / len(library) for t in per) / tot["n"], 3
            ),
            "baseline_depth_nearest": round(tot["depth_top1"] / tot["n"], 3),
            "alert_recall": round(tot["alerts"] / tot["n"], 3),
            "alert_precision": (
                round(tot["alerts_right"] / tot["alerts"], 3) if tot["alerts"] else None
            ),
            "by_type": {
                t: {
                    "queries": c["n"],
                    "precision_at_1": round(c["top1"] / c["n"], 3),
                    "alert_recall": round(c["alerts"] / c["n"], 3),
                }
                for t, c in sorted(per.items())
            },
        }

    false_matches = n_normal = 0
    for ep in normals:
        for end in (350, 500, 650, 820):
            m = best(ep, end)
            n_normal += 1
            false_matches += bool(m and m.similarity >= dv.ALERT_SIMILARITY)

    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 (developer tool on PATH)
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    result: dict[str, Any] = {
        "what": "S7d Deja Vu pattern matching on SYNTHETIC drilling data",
        "measured_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "commit": commit or None,
        "protocol": "library = seeded field wells 1-40; tau calibrated on precursor-free "
        "windows of training-field wells (seed 1); queries from other training-field "
        "episodes (seed 2), never in the library",
        "library": {"signatures": len(library), "by_type": dict(sorted(mix.items()))},
        "tau": round(tau, 4),
        "alert_similarity": dv.ALERT_SIMILARITY,
        "results": by_lead,
        "false_match_rate": {
            "precursor_free_windows": n_normal,
            "reaching_alert_similarity": false_matches,
            "rate": round(false_matches / n_normal, 4),
            "calibration_target": 0.01,
        },
        "latency_ms": {
            "p50": round(float(np.percentile(latencies, 50)), 1),
            "p95": round(float(np.percentile(latencies, 95)), 1),
            "library_size": len(library),
        },
        "notes": [
            "SYNTHETIC: every precursor comes from our own simulator; precision here says the "
            "matcher separates the planted shapes, not that it finds Assam incidents.",
            "Similarity = exp(-D/tau) is a similarity, never a probability.",
            "Weak on mechanical precursors (TIGHT, TORQUE): their planted signal is spiky and "
            "shape-poor at 30-s resolution; the classifiers carry those types.",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"dejavu_synthetic_{datetime.now(tz=UTC):%Y-%m-%d}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
