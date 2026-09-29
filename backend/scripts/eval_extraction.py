"""Score S2 extraction against the synthetic field's ground truth.

Reads ``s3://<raw bucket>/synthetic/truth.json`` (written by ``app.cli seed``) and the
extracted rows in the database, and writes ``eval/results/extraction_synthetic_<date>.json``.

This measures the pipeline on SYNTHETIC reports: reworded, unit-varied and 30% scanned,
but generated from a known vocabulary. It is an upper bound for real archives, not the
master plan §13.1 hand-annotated gold set, and must be quoted as such.

    cd backend && uv run python -m app.cli extract --all && uv run python scripts/eval_extraction.py
"""

import json
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.models import (
    CasingString,
    Document,
    Event,
    Formation,
    MudInterval,
    Well,
    Wellbore,
)
from app.db.session import session_scope
from app.extract.rules import hole_size_in
from app.storage.s3 import get_s3_client

MATCH_DEPTH_M = 15.0
OUT_DIR = Path(__file__).resolve().parents[2] / "eval" / "results"


def _prf(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(p, 4),
        "recall": round(r, 4),
        "f1": round(f1, 4),
    }


def _acc(hits: list[bool]) -> dict[str, float | int] | None:
    if not hits:
        return None
    return {"n": len(hits), "accuracy": round(sum(hits) / len(hits), 4)}


def _match(truth: list[dict[str, Any]], got: list[Event]) -> list[tuple[dict[str, Any], Event]]:
    """Greedy nearest-depth matching within one well (type not required: scored separately)."""
    pairs = sorted(
        (
            (abs(t["md_m"] - e.md_m), i, j)
            for i, t in enumerate(truth)
            for j, e in enumerate(got)
            if e.md_m is not None and abs(t["md_m"] - e.md_m) <= MATCH_DEPTH_M
        ),
    )
    used_t: set[int] = set()
    used_e: set[int] = set()
    out = []
    for _, i, j in pairs:
        if i in used_t or j in used_e:
            continue
        used_t.add(i)
        used_e.add(j)
        out.append((truth[i], got[j]))
    return out


def main() -> None:
    settings = get_settings()
    body = get_s3_client().get_object(Bucket=settings.s3_bucket_raw, Key="synthetic/truth.json")
    truth = json.loads(body["Body"].read())
    truth_wells = {w["name"]: w for w in truth["wells"]}
    scanned_docs = {d["file"] for d in truth.get("documents", []) if d["scanned"]}

    tp = fp = fn = 0
    type_hits: list[bool] = []
    subtype_hits: list[bool] = []
    sev_hits: list[bool] = []
    fm_hits: list[bool] = []
    date_hits: list[bool] = []
    depth_err: list[float] = []
    npt_err: list[float] = []
    resolved_hits: list[bool] = []
    mit_count_hits: list[bool] = []
    action_hits: list[bool] = []
    outcome_hits: list[bool] = []
    by_type: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    conf_correct: list[float] = []
    conf_wrong: list[float] = []
    casing_hits: dict[str, list[bool]] = defaultdict(list)
    mud_hits: dict[str, list[bool]] = defaultdict(list)
    per_doc: dict[str, list[int]] = {"scanned": [0, 0, 0], "text_layer": [0, 0, 0]}
    wells_scored = 0

    with session_scope() as s:
        fm_names = {f.id: f.name for f in s.scalars(select(Formation))}
        ingested = {d.filename: d for d in s.scalars(select(Document))}
        for well in s.scalars(select(Well).order_by(Well.id)):
            tw = truth_wells.get(well.canonical_name)
            if tw is None or tw["status"] == "planned":
                continue
            docs = [d for d in truth.get("documents", []) if d["well"] == tw["name"]]
            if not any(d["file"] in ingested for d in docs):
                continue  # a partial seed (CI) ingests only some wells' reports
            # Only events some ingested report mentions can be found.
            reachable = {eid for d in docs if d["file"] in ingested for eid in d["event_ids"]}
            t_events = [e for e in tw["events"] if e["event_id"] in reachable]
            wells_scored += 1
            got = list(
                s.scalars(
                    select(Event)
                    .where(Event.well_id == well.id, Event.status == "active")
                    .options(selectinload(Event.mitigations), selectinload(Event.evidence))
                )
            )
            pairs = _match(t_events, got)
            tp += len(pairs)
            fp += len(got) - len(pairs)
            fn += len(t_events) - len(pairs)
            matched_t = {t["event_id"] for t, _ in pairs}
            for t in t_events:
                by_type[t["event_type"]][2 if t["event_id"] not in matched_t else 0] += 1
            for e in got:
                if all(e is not g for _, g in pairs):
                    by_type[e.event_type][1] += 1
            for t, e in pairs:
                ok_type = t["event_type"] == e.event_type
                type_hits.append(ok_type)
                if t["subtype"]:
                    subtype_hits.append(t["subtype"] == e.subtype)
                sev_hits.append(t["severity"] == e.severity)
                fm_hits.append(fm_names.get(e.formation_id or -1) == t["formation"])
                date_hits.append(
                    e.event_date is not None and e.event_date.isoformat() == t["start"][:10]
                )
                depth_err.append(abs(t["md_m"] - (e.md_m or 0)))
                if e.npt_hours is not None:
                    npt_err.append(abs(t["total_npt_hours"] - e.npt_hours))
                resolved_hits.append(e.resolved is t["resolved"])
                tm, em = t["mitigations"], sorted(e.mitigations, key=lambda m: m.seq)
                mit_count_hits.append(len(tm) == len(em))
                for k, m in enumerate(tm):
                    action_hits.append(k < len(em) and em[k].action_code == m["action_code"])
                    outcome_hits.append(k < len(em) and em[k].outcome == m["outcome"])
                correct = ok_type and abs(t["md_m"] - (e.md_m or 0)) <= 2
                (conf_correct if correct else conf_wrong).append(e.confidence)

            # Per-document detection (which reports the pipeline read an event from).
            for d in docs:
                row = ingested.get(d["file"])
                if row is None or row.doc_type != "DDR":
                    continue
                bucket = per_doc["scanned" if d["file"] in scanned_docs else "text_layer"]
                cited = {e.id for e in got if any(ev.document_id == row.id for ev in e.evidence)}
                expected = {e.id for t, e in pairs if t["event_id"] in d["event_ids"]}
                bucket[0] += len(cited & expected)
                bucket[1] += len(cited - expected)
                bucket[2] += len(d["event_ids"]) - len(cited & expected)

            # Casing and mud (from the WCR), matched in depth order.
            wb = s.scalar(select(Wellbore).where(Wellbore.well_id == well.id).order_by(Wellbore.id))
            if wb is None or not any(
                d["doc_type"] == "WCR" and d["file"] in ingested for d in docs
            ):
                continue
            cs = list(
                s.scalars(
                    select(CasingString)
                    .where(CasingString.wellbore_id == wb.id)
                    .options(selectinload(CasingString.cement_jobs))
                    .order_by(CasingString.shoe_md_m)
                )
            )
            for k, tc in enumerate(tw["casing"]):
                c = cs[k] if k < len(cs) else None
                cj = c.cement_jobs[0] if c and c.cement_jobs else None
                casing_hits["od_in"].append(
                    c is not None and c.od_in == hole_size_in(tc["od_label"])
                )
                casing_hits["hole_size_in"].append(
                    c is not None and c.hole_size_in == hole_size_in(tc["hole_label"])
                )
                casing_hits["shoe_md_m"].append(
                    c is not None
                    and c.shoe_md_m is not None
                    and abs(c.shoe_md_m - tc["shoe_md_m"]) <= 1
                )
                casing_hits["toc_md_m"].append(
                    cj is not None
                    and cj.toc_md_m is not None
                    and abs(cj.toc_md_m - tc["cement_top_md_m"]) <= 1
                )
                casing_hits["returns"].append(cj is not None and cj.returns == tc["returns"])
            ms = list(
                s.scalars(
                    select(MudInterval)
                    .where(MudInterval.wellbore_id == wb.id)
                    .order_by(MudInterval.md_from_m)
                )
            )
            for k, tm in enumerate(tw["mud"]):
                m = ms[k] if k < len(ms) else None
                mud_hits["interval"].append(
                    m is not None
                    and abs(m.md_from_m - tm["md_from_m"]) <= 1
                    and abs(m.md_to_m - tm["md_to_m"]) <= 1
                )
                mud_hits["mw_sg"].append(
                    m is not None and m.mw_sg is not None and abs(m.mw_sg - tm["mw_sg"]) <= 0.01
                )
                mud_hits["mud_type"].append(m is not None and m.mud_type == tm["mud_type"])

    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 (developer tool on PATH)
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    result = {
        "what": "S2 extraction vs synthetic ground truth (NOT the §13.1 real-report gold set)",
        "measured_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "commit": sha or None,
        "wells_scored": wells_scored,
        "match_rule": f"same well, |MD| <= {MATCH_DEPTH_M} m, greedy nearest",
        "events": _prf(tp, fp, fn),
        "events_by_type": {k: _prf(*v) for k, v in sorted(by_type.items())},
        "ddr_event_detection": {k: _prf(*v) for k, v in per_doc.items()},
        "fields_on_matched_events": {
            "event_type": _acc(type_hits),
            "subtype": _acc(subtype_hits),
            "severity": _acc(sev_hits),
            "formation": _acc(fm_hits),
            "event_date": _acc(date_hits),
            "resolved": _acc(resolved_hits),
            "depth_abs_error_m": {
                "mean": round(statistics.fmean(depth_err), 2) if depth_err else None,
                "max": round(max(depth_err), 2) if depth_err else None,
            },
            "npt_abs_error_h": {
                "mean": round(statistics.fmean(npt_err), 3) if npt_err else None,
                "max": round(max(npt_err), 2) if npt_err else None,
            },
        },
        "mitigations": {
            "count_exact": _acc(mit_count_hits),
            "action_code_in_order": _acc(action_hits),
            "outcome_in_order": _acc(outcome_hits),
        },
        "casing": {k: _acc(v) for k, v in casing_hits.items()},
        "mud": {k: _acc(v) for k, v in mud_hits.items()},
        "confidence_calibration": {
            "mean_when_correct": round(statistics.fmean(conf_correct), 3) if conf_correct else None,
            "mean_when_wrong": round(statistics.fmean(conf_wrong), 3) if conf_wrong else None,
            "n_wrong": len(conf_wrong),
        },
        "notes": [
            "Severity for TIGHT/TORQUE is drawn at random by the generator (not from overpull/"
            "torque), so severity accuracy for those types is capped near 50% by design.",
            "Kick subtypes (gas/water/oil) are never written in the synthetic reports; "
            "extraction leaves them null rather than guessing, which scores as a subtype miss.",
            "Rule phrase lists are general drilling vocabulary, but the synthetic reports use "
            "a fixed vocabulary too; expect lower scores on real reports.",
        ],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"extraction_synthetic_{datetime.now(tz=UTC):%Y-%m-%d}.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    print(f"wrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
