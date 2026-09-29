"""Score the S7a offset prior leave-one-well-out on the seeded SYNTHETIC field.

For every completed well W with formation tops, the risk profile is computed exactly as the
API serves it: W's own events are never used and the basin base rates exclude W. Its
P(event | formation) predictions are scored against what W actually recorded, by the Brier
score (master plan §7.3 baseline table: the offset prior must beat the unweighted "fraction
of offsets with the event in the formation" on held-out wells).

Methods, all scored on the same (well, formation, event type) cells:

- ``weighted``: the served estimate (AT_FORMATION distances, default radius and sigma);
- ``weighted_surface``: the same with surface distances;
- ``unweighted_offsets``: fraction of offsets within the radius that had the event in the
  formation (the plan's baseline); the basin base rate when no offset reached it;
- ``equal_weights_with_prior``: ablation, the served model with every weight 1 (sigma → ∞,
  no similarity): separates the distance weighting from the basin prior's smoothing;
- ``formation_frequency``: that fraction over every other drilled well in the field;
- ``basin_base_rate``: one rate per event type.

Uncertainty: bootstrap over held-out wells (2,000 resamples) for every score and for the
paired difference against ``weighted``. A sigma sweep is reported as sensitivity only; the
default is not tuned on these wells.

    cd backend && uv run python scripts/eval_risk_prior.py
"""

import json
import random
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.db.models import Event, Well
from app.db.session import session_scope
from app.risk import core, prior

RESAMPLES = 2000
SIGMA_SWEEP_KM = (2.5, 5.0, 10.0)
BINS = (0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0001)
OUT_DIR = Path(__file__).resolve().parents[2] / "eval" / "results"

Cell = tuple[int, str, str]  # (held-out well, formation, event type)


def _brier(cells: list[Cell], p: dict[Cell, float], y: dict[Cell, int]) -> float:
    return statistics.fmean((p[c] - y[c]) ** 2 for c in cells)


def _ci90(xs: list[float]) -> list[float]:
    xs = sorted(xs)
    return [round(xs[len(xs) // 20], 5), round(xs[-(len(xs) // 20) - 1], 5)]


def _bootstrap(
    wells: list[int],
    by_well: dict[int, list[Cell]],
    methods: dict[str, dict[Cell, float]],
    y: dict[Cell, int],
) -> dict[str, dict[str, Any]]:
    rng = random.Random(121)  # noqa: S311 (bootstrap, not cryptography)
    draws: dict[str, list[float]] = defaultdict(list)
    diffs: dict[str, list[float]] = defaultdict(list)
    for _ in range(RESAMPLES):
        sample = [rng.choice(wells) for _ in wells]
        cells = [c for w in sample for c in by_well[w]]
        base = _brier(cells, methods["weighted"], y)
        for name, p in methods.items():
            b = _brier(cells, p, y)
            draws[name].append(b)
            if name != "weighted":
                diffs[name].append(b - base)
    out: dict[str, dict[str, Any]] = {}
    for name, xs in draws.items():
        out[name] = {"ci90": _ci90(xs)}
        if name in diffs:
            out[name]["minus_weighted_ci90"] = _ci90(diffs[name])
            out[name]["weighted_better_share"] = round(
                sum(x > 0 for x in diffs[name]) / len(diffs[name]), 4
            )
    return out


def _calibration(
    cells: list[Cell], p: dict[Cell, float], y: dict[Cell, int]
) -> list[dict[str, Any]]:
    rows = []
    for lo, hi in pairwise(BINS):
        inside = [c for c in cells if lo <= p[c] < hi]
        if inside:
            rows.append(
                {
                    "bin": [lo, min(hi, 1.0)],
                    "n": len(inside),
                    "mean_predicted": round(statistics.fmean(p[c] for c in inside), 4),
                    "observed_rate": round(statistics.fmean(y[c] for c in inside), 4),
                }
            )
    return rows


def main() -> None:
    y: dict[Cell, int] = {}
    methods: dict[str, dict[Cell, float]] = defaultdict(dict)
    sweep: dict[float, dict[Cell, float]] = defaultdict(dict)
    by_well: dict[int, list[Cell]] = defaultdict(list)
    with session_scope() as s:
        drilled = [w for w in s.scalars(select(Well).order_by(Well.id)) if w.status != "planned"]
        types = sorted(set(s.scalars(select(Event.event_type).where(Event.status == "active"))))
        wbs = prior._primary_wellbores(s, [w.id for w in drilled])
        tops = prior._tops(s, list(wbs.values()))
        events = prior._events(s, [w.id for w in drilled])
        penetrated = {w: {t.name for t in tops.get(wb, [])} for w, wb in wbs.items()}
        fm_id = {t.name: t.formation_id for ts in tops.values() for t in ts}
        held_out = [w for w in drilled if w.status == "completed" and penetrated.get(w.id)]

        for w in held_out:
            prof = prior.risk_profile(s, w.id, event_types=types)
            surf = prior.risk_profile(s, w.id, event_types=types, mode="SURFACE")
            surf_p = {
                (iv.formation, r.event_type): r.probability
                for iv in surf.intervals
                for r in iv.risks
            }
            sweeps = {
                sig: {
                    (iv.formation, r.event_type): r.probability
                    for iv in prior.risk_profile(s, w.id, event_types=types, sigma_km=sig).intervals
                    for r in iv.risks
                }
                for sig in SIGMA_SWEEP_KM
            }
            others = [o for o in drilled if o.id != w.id]
            for iv in prof.intervals:
                reached = [o.id for o in others if iv.formation in penetrated.get(o.id, set())]
                for r in iv.risks:
                    cell = (w.id, iv.formation, r.event_type)
                    y[cell] = int(bool(events.get((w.id, fm_id[iv.formation], r.event_type))))
                    methods["weighted"][cell] = r.probability
                    methods["weighted_surface"][cell] = surf_p[(iv.formation, r.event_type)]
                    methods["unweighted_offsets"][cell] = (
                        r.offsets_with_event / r.offsets_total if r.offsets_total else r.base_rate
                    )
                    hits = sum(
                        1 for o in reached if events.get((o, fm_id[iv.formation], r.event_type))
                    )
                    methods["formation_frequency"][cell] = (
                        hits / len(reached) if reached else r.base_rate
                    )
                    methods["basin_base_rate"][cell] = r.base_rate
                    alpha, beta_ = core.prior_params(r.base_rate)
                    methods["equal_weights_with_prior"][cell] = (r.offsets_with_event + alpha) / (
                        r.offsets_total + alpha + beta_
                    )
                    for sig, ps in sweeps.items():
                        sweep[sig][cell] = ps[(iv.formation, r.event_type)]
                    by_well[w.id].append(cell)

    cells = [c for w in by_well for c in by_well[w]]
    wells = list(by_well)
    scores = {name: round(_brier(cells, p, y), 5) for name, p in methods.items()}
    boot = _bootstrap(wells, by_well, methods, y)
    base = scores["basin_base_rate"]
    per_type = {
        t: {
            "cells": sum(1 for c in cells if c[2] == t),
            "positives": sum(y[c] for c in cells if c[2] == t),
            **{
                name: round(_brier([c for c in cells if c[2] == t], p, y), 5)
                for name, p in methods.items()
            },
        }
        for t in sorted({c[2] for c in cells})
    }
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 (developer tool on PATH)
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    result: dict[str, Any] = {
        "what": "S7a offset prior, leave-one-well-out Brier score on the SYNTHETIC seeded field",
        "measured_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "commit": commit or None,
        "protocol": "each completed well held out in turn; its own events never used; "
        "base rates exclude it; cells = (well, formation it penetrated, event type)",
        "radius_km": prior.DEFAULT_RADIUS_KM,
        "sigma_km": prior.DEFAULT_RADIUS_KM / 2,
        "held_out_wells": len(wells),
        "cells": len(cells),
        "positive_cells": sum(y.values()),
        "event_types": sorted({c[2] for c in cells}),
        "brier": {
            name: {
                "score": score,
                "skill_vs_base_rate": round(1 - score / base, 4) if base else None,
                **boot[name],
            }
            for name, score in sorted(scores.items(), key=lambda kv: kv[1])
        },
        "brier_by_event_type": per_type,
        "calibration_weighted": _calibration(cells, methods["weighted"], y),
        "sensitivity_sigma_km": {
            str(sig): round(_brier(cells, p, y), 5) for sig, p in sorted(sweep.items())
        },
        "notes": [
            "Synthetic hazards are planted per formation with spatial structure; the ranking "
            "of methods here says how well each recovers that structure, not how it will do on "
            "Assam wells.",
            "minus_weighted_ci90 is the bootstrap interval of (method - weighted): an interval "
            "above 0 means the served estimate is better on these wells.",
            "The sigma sweep is sensitivity only; the default (radius / 2) was fixed before "
            "this evaluation and is not re-tuned on it.",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"risk_prior_synthetic_{datetime.now(tz=UTC):%Y-%m-%d}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "brier_by_event_type"},
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
