"""The Déjà Vu overlay (F4): an alert's live 30 minutes beside the matched run-up.

Both sides are rebuilt the way the matcher saw them: the live window is the 180 stored
samples ending at the alert's data time (gaps held at the last value, as the scorer's
buffer does) passed through `dejavu.prepare`; the matched segment is cut from the stored
signature at the offset implied by the recorded minutes-before-event."""

from datetime import datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts.service import _get
from app.api.v1.schemas.realtime import DejaVuOverlay
from app.core.errors import NotFoundError
from app.db.models import Well
from app.db.models.realtime import PatternSignature, RtSample
from app.risk import dejavu as dv

RAW = (
    "torque_knm", "hookload_kn", "spp_kpa", "rop_m_h", "wob_kn", "flow_in_lpm",
    "flow_out_lpm", "pit_volume_m3", "gas_pct",
)  # fmt: skip


def _round(d: dict[str, np.ndarray]) -> dict[str, list[float]]:
    return {c: [round(float(x), 3) for x in d[c]] for c in dv.CHANNELS}


def _live(
    session: Session, wellbore_id: int | None, t_data: datetime
) -> dict[str, np.ndarray] | None:
    if wellbore_id is None:
        return None
    rows = list(
        session.scalars(
            select(RtSample)
            .where(RtSample.wellbore_id == wellbore_id, RtSample.ts <= t_data)
            .order_by(RtSample.ts.desc())
            .limit(dv.QUERY_STEPS)
        )
    )[::-1]
    if len(rows) < dv.QUERY_STEPS:
        return None  # the replay that raised it was overwritten by a later run
    raw: dict[str, np.ndarray] = {}
    for c in RAW:
        vals, last = [], 0.0
        for r in rows:
            v = getattr(r, c)
            last = float(v) if v is not None else last
            vals.append(last)
        raw[c] = np.asarray(vals)
    return dv.prepare(raw)


def dejavu(session: Session, alert_id: int) -> DejaVuOverlay:
    a, _ = _get(session, alert_id)
    # The match is the alert's own detail, or that of a Déjà Vu candidate fused into it.
    detail, t_data = a.detail or {}, a.t_data
    for f in detail.get("fused", []):
        if f.get("source") == "DEJA_VU" and "matched_signature_id" in f.get("detail", {}):
            detail, t_data = f["detail"], datetime.fromisoformat(f["t_data"])
            break
    sid = detail.get("matched_signature_id")
    sig = session.get(PatternSignature, sid) if sid is not None else None
    if sig is None:
        raise NotFoundError(f"Alert {alert_id} has no Déjà Vu match.", {"alert_id": alert_id})
    rec = next(
        (m for m in detail.get("matches", []) if m.get("signature_id") == sid),
        {"similarity": a.score or 0.0, "minutes_before_event": 0.0},
    )
    mbe = float(rec["minutes_before_event"])
    offset = dv.SIGNATURE_STEPS - dv.QUERY_STEPS - round(mbe * 60 / sig.dt_s)
    offset = min(max(offset, 0), dv.SIGNATURE_STEPS - dv.QUERY_STEPS)
    full = {c: np.asarray(sig.channels[c], dtype=float) for c in dv.CHANNELS}
    live = _live(session, a.wellbore_id, t_data)
    well_name = session.scalar(select(Well.canonical_name).where(Well.id == sig.well_id))
    return DejaVuOverlay(
        alert_id=a.id,
        signature_id=sig.id,
        event_type=sig.event_type,
        matched_well_id=sig.well_id,
        matched_well_name=well_name,
        matched_event_id=sig.event_id,
        formation=sig.formation,
        similarity=float(rec["similarity"]),
        minutes_before_event=mbe,
        dt_s=sig.dt_s,
        channels=list(dv.CHANNELS),
        live=_round(live) if live is not None else None,
        matched={c: v[offset : offset + dv.QUERY_STEPS] for c, v in _round(full).items()},
        signature=_round(full),
        note=(
            "Channels in operating state only (mechanical while drilling, hydraulic while "
            "pumping, pit relative to the window start). Similarity is not a probability: "
            "compare the shapes before acting."
        ),
    )
