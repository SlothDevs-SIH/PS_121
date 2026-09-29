"""Score the S7b real-time classifiers on the SYNTHETIC data (no database needed).

Two numbers per event type, both at the model's own alert threshold:

- ``cross_validation``: grouped 5-fold out-of-fold predictions over the training field
  (wells 61+; folds split by well), isotonic calibration fitted on those predictions;
- ``held_out_field``: the final models on the episodes of the seeded field's wells (1-40),
  which the models never saw.

Each against chance (the positive rate) and a one-feature "physics threshold" baseline, with
false alarms per 12 h of precursor-free drilling (one per minute-row above the threshold,
no hysteresis credit), events caught within 30 min, and the median lead.

Honesty note: the precursors are planted by our own simulator, so these numbers measure
whether the pipeline recovers them, not skill on Assam wells.

    cd backend && uv run python scripts/eval_realtime.py
"""

import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.risk import realtime_model as rm

OUT_DIR = Path(__file__).resolve().parents[2] / "eval" / "results"


def _rows(eps: list[Any]) -> list[rm.Row]:
    return [r for k, ep in enumerate(eps) for r in rm.rows_of(ep, k)]


def main() -> None:
    t = time.perf_counter()
    train_rows = _rows(rm.episodes_for(120, rm.TRAINING_WELLS_FROM))
    bundle = rm.train(train_rows)
    train_s = time.perf_counter() - t
    held = rm.evaluate(bundle, _rows(rm.episodes_for(40, 1)))
    x = train_rows[0].x
    t = time.perf_counter()
    for _ in range(200):
        bundle.score(x)
    score_ms = (time.perf_counter() - t) / 200 * 1000
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 (developer tool on PATH)
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    result: dict[str, Any] = {
        "what": "S7b real-time classifiers on SYNTHETIC drilling data (planted precursors)",
        "measured_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "commit": commit or None,
        "model": rm.MODEL_VERSION,
        "horizon_min": rm.HORIZON_STEPS * 10 / 60,
        "protocol": "grouped 5-fold CV by well on the training field (wells 61-180); then "
        "the final models on the seeded field's wells 1-40, never seen in training",
        "cross_validation": bundle.metrics,
        "held_out_field": held,
        "train_seconds": round(train_s, 1),
        "score_ms_per_sample_all_types": round(score_ms, 2),
        "notes": [
            "SYNTHETIC: precursors are planted by app/synthetic/realtime.py; these numbers say "
            "the pipeline recovers them, not how it would do on Assam wells.",
            "false_alarms_per_12h counts every minute-row above the threshold on precursor-"
            "free time; the stream's hysteresis (2 in a row) and alert budget lower the rate "
            "that reaches a user.",
            "median_lead_min is capped at the 30-min horizon (rows further ahead are not "
            "labelled), so 30.0 means 'as early as the label allows'.",
            "TIGHT and INSTAB have no model: their planted precursors overlap STUCK and "
            "TORQUE and there are too few episodes; Deja Vu and the physics rules cover them.",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"realtime_synthetic_{datetime.now(tz=UTC):%Y-%m-%d}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    summary = {
        split: {
            et: {
                k: v[k]
                for k in (
                    "pr_auc",
                    "pr_auc_physics_threshold",
                    "false_alarms_per_12h",
                    "events",
                    "events_caught",
                    "median_lead_min",
                )
            }
            for et, v in result[split]["types"].items()
        }
        for split in ("cross_validation", "held_out_field")
    }
    print(json.dumps(summary, indent=2))
    print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
