"""Score the S8 Mitigation Effectiveness Ledger against the planted success rates.

Criterion (master plan §13.7): the ledger's ranking matches the planted ranking with
Spearman rho ≥ 0.8 for actions with n ≥ 5, and its 90% credible intervals cover the planted
rates at roughly the nominal 90%.

Two measurements, both on SYNTHETIC data, and quoted as such:

1. **Pipeline**: the ledger exactly as the API serves it, over the events and mitigations
   *extracted* from the seeded field's reports (ingest → OCR → extraction → ledger).
2. **Scale check**: the same ledger mathematics (``app.ledger.core``) on generator ground
   truth for wells *outside* the seeded field: ten independent fields of the seeded size
   (how much rho varies at this sample size) and all of them pooled (whether the method
   converges on the planted ranking as the evidence grows).

    cd backend && uv run python scripts/eval_ledger.py
"""

import json
import statistics
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scipy.stats import spearmanr

from app.core.config import get_settings
from app.db.session import session_scope
from app.ledger import core
from app.ledger.service import ledger
from app.storage.s3 import get_s3_client
from app.synthetic import model as sm
from app.synthetic.generator import Event as TruthEvent
from app.synthetic.generator import Well as TruthWell
from app.synthetic.generator import generate

MIN_N = 5  # §13.7
FIELDS = 10
OUT_DIR = Path(__file__).resolve().parents[2] / "eval" / "results"


@dataclass
class Estimate:
    event_type: str
    action: str
    n: int
    uses: int
    successes: int
    posterior_mean: float | None
    ci90_low: float | None
    ci90_high: float | None

    @property
    def planted(self) -> float:
        return sm.PLANTED_SUCCESS[self.event_type][self.action]

    @property
    def covered(self) -> bool | None:
        if self.ci90_low is None or self.ci90_high is None:
            return None
        return self.ci90_low <= self.planted <= self.ci90_high


def _rho(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    return round(float(spearmanr(xs, ys).statistic), 4)


def score(estimates: list[Estimate], min_n: int = MIN_N) -> dict[str, Any]:
    known = [e for e in estimates if e.event_type in sm.PLANTED_SUCCESS]
    eligible = [e for e in known if e.n >= min_n and e.posterior_mean is not None]
    concordant = pairs = 0
    top_hits = top_total = 0
    for et in sm.PLANTED_SUCCESS:
        group = [e for e in eligible if e.event_type == et]
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                if a.planted == b.planted:
                    continue
                pairs += 1
                pm_a, pm_b = a.posterior_mean or 0.0, b.posterior_mean or 0.0
                concordant += (pm_a - pm_b) * (a.planted - b.planted) > 0
        if len(group) >= 2:
            top_total += 1
            best_ledger = max(group, key=lambda e: (e.posterior_mean or 0.0, e.n))
            top_hits += best_ledger.planted == max(e.planted for e in group)
    covered = [e.covered for e in known if e.covered is not None]
    return {
        "pairs_total": len(known),
        "pairs_eligible": len(eligible),
        "spearman_rho": _rho(
            [e.posterior_mean or 0.0 for e in eligible], [e.planted for e in eligible]
        ),
        "usage_frequency_baseline_rho": _rho(
            [float(e.uses) for e in eligible], [e.planted for e in eligible]
        ),
        "within_type_pairwise_concordance": (
            {"concordant": concordant, "pairs": pairs, "rate": round(concordant / pairs, 4)}
            if pairs
            else None
        ),
        "best_action_matches_planted": {"types": top_total, "matches": top_hits},
        "ci90_coverage": (
            {
                "covered": sum(covered),
                "total": len(covered),
                "rate": round(sum(covered) / len(covered), 4),
            }
            if covered
            else None
        ),
    }


def _table(estimates: list[Estimate]) -> list[dict[str, Any]]:
    return [
        {
            "event_type": e.event_type,
            "action": e.action,
            "n": e.n,
            "successes": e.successes,
            "posterior_mean": e.posterior_mean,
            "ci90": [e.ci90_low, e.ci90_high],
            "planted": e.planted,
            "covered": e.covered,
        }
        for e in sorted(estimates, key=lambda x: (x.event_type, -(x.posterior_mean or 0)))
        if e.event_type in sm.PLANTED_SUCCESS
    ]


def pipeline() -> tuple[list[Estimate], dict[str, int]]:
    estimates: list[Estimate] = []
    scope = {"events": 0, "mitigations": 0}
    with session_scope() as s:
        for et in sm.PLANTED_SUCCESS:
            body = ledger(s, event_type=et, min_n=1)
            scope["events"] += body.scope.events
            scope["mitigations"] += body.scope.mitigations
            for e in body.ranked + body.insufficient:
                if e.action_code not in sm.PLANTED_SUCCESS[et]:
                    continue  # an extraction error (a code the generator never plants)
                estimates.append(
                    Estimate(
                        et,
                        e.action_code,
                        e.n,
                        e.n + e.unknown,
                        e.successes,
                        e.posterior_mean,
                        e.ci90_low,
                        e.ci90_high,
                    )
                )
    return estimates, scope


def _field_estimates(wells: list[TruthWell]) -> list[Estimate]:
    """Ledger mathematics on generator ground truth (outcome rule and recurrence included)."""
    lite: list[core.EventLite] = []
    raw: list[TruthEvent] = []
    for wi, w in enumerate(wells):
        for ev in w.events:
            day = datetime.fromisoformat(ev.start).date().toordinal()
            lite.append(core.EventLite(len(raw), wi, ev.event_type, ev.tvdss_m, day))
            raw.append(ev)
    by_type: dict[str, list[core.UseRecord]] = {}
    for el, ev in zip(lite, raw, strict=True):
        again = core.recurred(el, lite)
        for seq, m in enumerate(ev.mitigations, start=1):
            by_type.setdefault(ev.event_type, []).append(
                core.UseRecord(
                    m.action_code,
                    m.outcome,
                    seq=seq,
                    recurred=again and m.outcome == "success",
                    severity=ev.severity,
                )
            )
    out = []
    for et, uses in by_type.items():
        for s in core.summarise(uses):
            out.append(
                Estimate(
                    et,
                    s.action_code,
                    s.n,
                    s.n + s.unknown,
                    s.successes,
                    s.posterior_mean,
                    s.ci90_low,
                    s.ci90_high,
                )
            )
    return out


def scale_check(seeded: set[str], field_size: int) -> dict[str, Any]:
    synthetic = generate(field_size * (FIELDS + 1) + 5)
    fresh = [w for w in synthetic.wells if w.name not in seeded and w.status != "planned"]
    fields = [fresh[i * field_size : (i + 1) * field_size] for i in range(FIELDS)]
    per_field = [score(_field_estimates(f)) for f in fields]
    rhos = [r["spearman_rho"] for r in per_field if r["spearman_rho"] is not None]
    cov = [r["ci90_coverage"] for r in per_field if r["ci90_coverage"]]
    pooled_wells = [w for f in fields for w in f]
    pooled = _field_estimates(pooled_wells)
    return {
        "fields": FIELDS,
        "wells_per_field": field_size,
        "rho_per_field": rhos,
        "rho_median": round(statistics.median(rhos), 4) if rhos else None,
        "rho_min": min(rhos) if rhos else None,
        "fields_meeting_rho_0_8": sum(r >= 0.8 for r in rhos),
        "ci90_coverage_across_fields": {
            "covered": sum(c["covered"] for c in cov),
            "total": sum(c["total"] for c in cov),
            "rate": round(sum(c["covered"] for c in cov) / sum(c["total"] for c in cov), 4)
            if cov
            else None,
        },
        "pooled": {
            "wells": len(pooled_wells),
            "mitigations": sum(e.uses for e in pooled),
            **score(pooled),
            "table": _table(pooled),
        },
    }


def main() -> None:
    settings = get_settings()
    body = get_s3_client().get_object(Bucket=settings.s3_bucket_raw, Key="synthetic/truth.json")
    truth = json.loads(body["Body"].read())
    seeded = {w["name"] for w in truth["wells"]}
    drilled = sum(1 for w in truth["wells"] if w["status"] != "planned")

    estimates, scope = pipeline()
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 (developer tool on PATH)
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    result: dict[str, Any] = {
        "what": "S8 ledger vs planted success rates on SYNTHETIC data (master plan §13.7)",
        "measured_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "commit": commit or None,
        "criterion": "Spearman rho >= 0.8 over (event type, action) with n >= 5; "
        "90% credible intervals cover the planted rates at about 90%",
        "outcome_rule": core.OUTCOME_RULE,
        "pipeline": {
            "source": "events and mitigations extracted from the seeded field's reports",
            "wells_in_field": drilled,
            **scope,
            **score(estimates),
            "rho_with_n_ge_3": score(estimates, min_n=3)["spearman_rho"],
            "table": _table(estimates),
        },
        "scale_check": {
            "source": "generator ground truth for wells outside the seeded field "
            "(no extraction step)",
            **scale_check(seeded, drilled),
        },
        "notes": [
            "Synthetic outcomes are independent draws at the planted rates, so there is no "
            "confounding by severity here; real records will have it (see the ledger caveat).",
            "rho pools (event type, action) pairs across event types, as §13.7 states it; "
            "within-type pairwise concordance and best-action matches are the per-type view.",
            "The usage-frequency baseline ranks actions by how often crews used them: the "
            "generator draws first choices independently of effectiveness, so it should not "
            "recover the ranking.",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"ledger_synthetic_{datetime.now(tz=UTC):%Y-%m-%d}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    summary = {k: v for k, v in result["pipeline"].items() if k != "table"}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    sc = {k: v for k, v in result["scale_check"].items() if k != "pooled"}
    print(json.dumps(sc, indent=2, ensure_ascii=False))
    pooled = {k: v for k, v in result["scale_check"]["pooled"].items() if k != "table"}
    print(json.dumps(pooled, indent=2, ensure_ascii=False))
    print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
