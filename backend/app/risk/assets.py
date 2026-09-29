"""Real-time assets built once at seed time (B4) and loaded by the stream service.

- the classifier bundle (S7b), trained on a SYNTHETIC training field of wells that are not
  in the seeded field, with its grouped cross-validation metrics;
- the Déjà Vu library (S7d): the 90 minutes before every real-time event of the seeded
  wells, linked to the database event it preceded when one was extracted, and tau
  calibrated on precursor-free windows of the training field;
- the replay file of the drilling well (S12), in oilfield units with the default CSV
  mnemonics, and its truth file (what was planted, when).

Objects go to the raw bucket under models/realtime/ and replay/. The bundle is a joblib
pickle we wrote ourselves; it is trusted input for that reason only.
"""

import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Event, MudInterval, Well, Wellbore
from app.db.models.realtime import ChannelMapping, PatternSignature
from app.risk import dejavu as dv
from app.risk import realtime_model as rm
from app.risk.prior import risk_profile
from app.storage.s3 import get_s3_client
from app.stream import mapping as mp
from app.synthetic import realtime as rt
from app.synthetic.generator import SyntheticField

PREFIX = "models/realtime/"
MODEL_KEY = f"{PREFIX}{rm.MODEL_VERSION}.joblib"
METRICS_KEY = f"{PREFIX}{rm.MODEL_VERSION}.metrics.json"
DEJAVU_KEY = f"{PREFIX}dejavu.json"
REPLAY_T0 = datetime(2026, 9, 28, 18, 0, tzinfo=UTC)
EVENT_MATCH_M = 15.0  # a signature belongs to the extracted event of its type within 15 m MD
CALIBRATION_ENDS = (400, 600, 800)  # query windows ending here in each normal episode


def replay_key(well_name: str) -> str:
    return f"replay/{well_name}.csv"


def replay_truth_key(well_name: str) -> str:
    return f"replay/{well_name}.truth.json"


def _put(key: str, body: bytes, content_type: str) -> None:
    get_s3_client().put_object(
        Bucket=get_settings().s3_bucket_raw, Key=key, Body=body, ContentType=content_type
    )


def get_object(key: str) -> bytes:
    obj = get_s3_client().get_object(Bucket=get_settings().s3_bucket_raw, Key=key)
    return obj["Body"].read()


def pre_event_window(ep: rt.Episode) -> dict[str, np.ndarray]:
    return {c: v[rt.PRE_STEPS - dv.SIGNATURE_STEPS : rt.PRE_STEPS] for c, v in ep.data.items()}


def signature_of(ep: rt.Episode, sid: int, well_id: int | None = None) -> dv.Signature:
    pre = pre_event_window(ep)
    return dv.Signature(
        sid,
        ep.planted[0].event_type,
        dv.prepare(pre),
        float(np.mean(pre["wob_kn"] > 10)),
        ep.hole_size_in,
        well_id=well_id,
    )


def query_window(d: dict[str, np.ndarray], end: int) -> tuple[dict[str, np.ndarray], float]:
    """The prepared 30-min query ending at sample `end` and its drilling share."""
    w = {c: v[end - dv.QUERY_STEPS : end] for c, v in d.items()}
    return dv.prepare(w), float(np.mean(w["wob_kn"] > 10))


def link_event(session: Session, well_id: int, event_type: str, md_m: float) -> int | None:
    """The extracted event of this type nearest `md_m` in the well (within 15 m), if any."""
    rows = session.execute(
        select(Event.id, Event.md_m).where(
            Event.well_id == well_id,
            Event.event_type == event_type,
            Event.md_m.between(md_m - EVENT_MATCH_M, md_m + EVENT_MATCH_M),
        )
    ).all()
    if not rows:
        return None
    return int(min(rows, key=lambda r: abs(float(r[1]) - md_m))[0])


# ─── Build ────────────────────────────────────────────────────────────────────


def build_model(train_wells: int) -> rm.ModelBundle:
    eps = rm.episodes_for(train_wells, rm.TRAINING_WELLS_FROM)
    rows = [r for k, ep in enumerate(eps) for r in rm.rows_of(ep, k)]
    bundle = rm.train(rows)
    bundle.metrics["training_wells"] = f"synthetic training field, wells {rm.TRAINING_WELLS_FROM}+"
    _put(MODEL_KEY, bundle.dumps(), "application/octet-stream")
    _put(METRICS_KEY, json.dumps(bundle.metrics, indent=2).encode(), "application/json")
    return bundle


def build_library(session: Session, field: SyntheticField) -> list[dv.Signature]:
    """pattern_signature rows for every real-time event of the seeded, completed wells."""
    ids = dict(session.execute(select(Well.canonical_name, Well.id)).tuples().all())
    events = {ev.event_id: ev for w in field.wells if w.status == "completed" for ev in w.events}
    session.execute(delete(PatternSignature).where(PatternSignature.source == "synthetic"))
    library: list[dv.Signature] = []
    completed = [w for w in field.wells if w.status == "completed"]
    for ep in rm.episodes_of(completed):
        if not ep.planted or ep.well not in ids or ep.source_event_id not in events:
            continue
        ev = events[ep.source_event_id]
        sig = signature_of(ep, 0, ids[ep.well])
        row = PatternSignature(
            event_id=link_event(session, ids[ep.well], ev.event_type, ev.md_m),
            well_id=ids[ep.well],
            event_type=ev.event_type,
            formation=ev.formation,
            hole_size_in=ep.hole_size_in,
            md_m=ev.md_m,
            tvdss_m=ev.tvdss_m,
            dt_s=rt.DT_S,
            channels={c: [round(float(v), 4) for v in a] for c, a in sig.channels.items()},
            drilling_share=sig.drilling_share,
            source="synthetic",
        )
        session.add(row)
        session.flush()
        sig.id, sig.event_id = row.id, row.event_id
        library.append(sig)
    return library


def calibrate(library: list[dv.Signature], calib_wells: int) -> dict[str, Any]:
    """tau from the best-match distances of precursor-free windows of the training field."""
    eps = [e for e in rm.episodes_for(calib_wells, rm.TRAINING_WELLS_FROM, seed=1) if not e.planted]
    dist: list[float] = []
    for ep in eps:
        for end in CALIBRATION_ENDS:
            q, share = query_window(ep.data, end)
            m = dv.search(q, library, 1.0, share, ep.hole_size_in, top=1)
            if m:
                dist.append(m[0].distance)
    tau = dv.calibrate_tau(dist)
    out = {
        "tau": round(tau, 5),
        "alert_similarity": dv.ALERT_SIMILARITY,
        "false_match_rate": 0.01,
        "calibration_windows": len(dist),
        "normal_distance_p1_p5_p50": [round(float(x), 4) for x in np.percentile(dist, [1, 5, 50])],
        "library_size": len(library),
        "note": "SYNTHETIC: calibrated on simulated precursor-free drilling windows",
    }
    _put(DEJAVU_KEY, json.dumps(out, indent=2).encode(), "application/json")
    return out


def seed_channel_mappings(session: Session) -> int:
    have = set(session.execute(select(ChannelMapping.source, ChannelMapping.mnemonic)).tuples())
    added = 0
    for source, maps in mp.DEFAULTS.items():
        for m in maps:
            if (source, m.mnemonic) not in have:
                session.add(
                    ChannelMapping(
                        source=source, mnemonic=m.mnemonic, channel=m.channel, unit=m.unit
                    )
                )
                added += 1
    return added


def build_replay(session: Session) -> dict[str, Any] | None:
    """The drilling well's replay file: drilling on from its TD into the next formation."""
    well = session.scalar(select(Well).where(Well.status == "drilling").order_by(Well.id).limit(1))
    if well is None or well.td_md_m is None:
        return None
    profile = risk_profile(session, well.id)
    ahead = next((i for i in profile.intervals if i.prognosed), None)
    if ahead is None:
        return None
    mud = session.execute(
        select(MudInterval.hole_size_in, MudInterval.mw_sg)
        .join(Wellbore, Wellbore.id == MudInterval.wellbore_id)
        .where(Wellbore.well_id == well.id)
        .order_by(MudInterval.md_to_m.desc())
        .limit(1)
    ).first()
    hole_in = float(mud[0]) if mud and mud[0] else 8.5
    mw = float(mud[1]) if mud and mud[1] else 1.3
    ep = rt.replay_episode(
        well.id, well.canonical_name, well.td_md_m, REPLAY_T0, ahead.top_md_m, hole_in, mw
    )
    body = mp.write_csv(REPLAY_T0, rt.DT_S, ep.data, mp.CSV_DEFAULTS)
    _put(replay_key(well.canonical_name), body.encode(), "text/csv")
    truth = {
        "well": well.canonical_name,
        "synthetic": True,
        "t0": REPLAY_T0.isoformat(),
        "dt_s": rt.DT_S,
        "rows": ep.n,
        "start_md_m": well.td_md_m,
        "next_formation": ahead.formation,
        "next_top_md_m_prognosed": ahead.top_md_m,
        "loss_in_next_formation": bool(
            ep.data["hole_depth_m"][ep.planted[1].start] >= ahead.top_md_m
        ),
        "rop_m_h_base": round(float(np.median(ep.data["rop_m_h"][ep.data["rop_m_h"] > 0])), 1),
        "planted": [
            {
                **asdict(p),
                "t_start": (REPLAY_T0 + timedelta(seconds=p.start * rt.DT_S)).isoformat(),
                "md_at_start_m": round(float(ep.data["hole_depth_m"][p.start]), 1),
            }
            for p in ep.planted
        ],
    }
    _put(
        replay_truth_key(well.canonical_name),
        json.dumps(truth, indent=2).encode(),
        "application/json",
    )
    return truth


def build_all(
    session: Session,
    field: SyntheticField,
    *,
    train_wells: int = 120,
    calib_wells: int = 40,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    bundle = build_model(train_wells)
    log(f"[realtime] classifiers {rm.MODEL_VERSION}: {bundle.metrics['rows']} rows")
    library = build_library(session, field)
    linked = sum(s.event_id is not None for s in library)
    log(f"[realtime] Deja Vu library: {len(library)} signatures, {linked} linked to events")
    dj = calibrate(library, calib_wells)
    log(f"[realtime] Deja Vu tau {dj['tau']} from {dj['calibration_windows']} windows")
    added = seed_channel_mappings(session)
    session.flush()
    truth = build_replay(session)
    log(f"[realtime] channel mappings added: {added}; replay: {truth and truth['well']}")
    return {"model": bundle.metrics, "dejavu": dj, "replay": truth}


# ─── Load ─────────────────────────────────────────────────────────────────────


def load_bundle() -> rm.ModelBundle:
    return rm.ModelBundle.loads(get_object(MODEL_KEY))


def load_dejavu() -> dict[str, Any]:
    out: dict[str, Any] = json.loads(get_object(DEJAVU_KEY))
    return out


def load_library(session: Session) -> list[dv.Signature]:
    rows = session.scalars(select(PatternSignature).order_by(PatternSignature.id)).all()
    return [
        dv.Signature(
            r.id,
            r.event_type,
            {c: np.asarray(v, dtype=float) for c, v in r.channels.items()},
            r.drilling_share,
            r.hole_size_in,
            well_id=r.well_id,
            event_id=r.event_id,
            meta={"formation": r.formation, "md_m": r.md_m, "tvdss_m": r.tvdss_m},
        )
        for r in rows
    ]


def load_mappings(session: Session, source: str) -> list[mp.ChannelMap]:
    rows = session.scalars(select(ChannelMapping).where(ChannelMapping.source == source)).all()
    return [mp.ChannelMap(r.mnemonic, r.channel, r.unit) for r in rows] or list(
        mp.DEFAULTS.get(source, ())
    )
