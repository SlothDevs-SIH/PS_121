"""Replay control and the real-time read side for the API (the stream service does the work).

Starting a replay creates a ``replay_session`` row; the stream service picks it up within a
second. Pause, resume, stop and speed change the row; the publisher follows it.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.schemas.realtime import RealtimeWindow, ReplaySessionOut, StreamStatus
from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError
from app.db.models import Well, Wellbore
from app.db.models.realtime import CHANNELS, ReplaySession, RtSample, RtScore
from app.normalise.wells_service import get_well_or_404
from app.risk import assets
from app.storage.s3 import get_s3_client

UNITS = {
    "bit_depth_m": "m",
    "hole_depth_m": "m",
    "hookload_kn": "kN",
    "wob_kn": "kN",
    "rpm": "rpm",
    "torque_knm": "kN.m",
    "spp_kpa": "kPa",
    "flow_in_lpm": "L/min",
    "flow_out_lpm": "L/min",
    "pit_volume_m3": "m3",
    "rop_m_h": "m/h",
    "gas_pct": "%",
}
STALE_AFTER = timedelta(seconds=60)
ACTIVE = ("pending", "running", "paused")


class ReplayStateError(AppError):
    status_code = 409
    code = "invalid_replay_state"


def _out(rs: ReplaySession, well: Well) -> ReplaySessionOut:
    return ReplaySessionOut.model_validate(
        {
            "id": rs.id,
            "well_id": rs.well_id,
            "well_name": well.canonical_name,
            "wellbore_id": rs.wellbore_id,
            "source_uri": rs.source_uri,
            "speed": rs.speed,
            "status": rs.status,
            "position": rs.position,
            "total_rows": rs.total_rows,
            "data_start": rs.data_start,
            "data_now": rs.data_now,
            "error": rs.error,
            "synthetic": well.synthetic,
            "created_at": rs.created_at,
            "updated_at": rs.updated_at,
        }
    )


def _latest_session(session: Session, well_id: int) -> ReplaySession | None:
    return session.scalar(
        select(ReplaySession)
        .where(ReplaySession.well_id == well_id)
        .order_by(ReplaySession.id.desc())
        .limit(1)
    )


def replay(session: Session, well_id: int, action: str, speed: float) -> ReplaySessionOut:
    well = get_well_or_404(session, well_id)
    cur = _latest_session(session, well_id)
    if action == "start":
        from app.stream.service import reset_wellbore

        wb = session.scalar(
            select(Wellbore.id).where(Wellbore.well_id == well_id).order_by(Wellbore.id).limit(1)
        )
        key = assets.replay_key(well.canonical_name)
        try:
            get_s3_client().head_object(Bucket=get_settings().s3_bucket_raw, Key=key)
        except ClientError as exc:
            raise NotFoundError(
                f"No replay file for {well.canonical_name}: run `python -m app.cli realtime`.",
                {"well_id": well_id, "key": key},
            ) from exc
        if wb is None:
            raise NotFoundError(f"Well {well_id} has no wellbore.", {"well_id": well_id})
        if cur is not None and cur.status in ACTIVE:
            cur.status = "stopped"
        reset_wellbore(session, wb)
        rs = ReplaySession(
            well_id=well_id,
            wellbore_id=wb,
            source_uri=f"s3://{get_settings().s3_bucket_raw}/{key}",
            speed=speed,
            status="pending",
            position=0,
        )
        session.add(rs)
        session.flush()
        session.refresh(rs)
        return _out(rs, well)
    if cur is None:
        raise NotFoundError(f"Well {well_id} has no replay session.", {"well_id": well_id})
    allowed = {
        "pause": ("pending", "running"),
        "resume": ("paused",),
        "stop": ACTIVE,
        "speed": ACTIVE,
    }[action]
    if cur.status not in allowed:
        raise ReplayStateError(f"Replay {cur.id} is {cur.status}; cannot {action} it.")
    if action == "pause":
        cur.status = "paused"
    elif action == "resume":
        cur.status = "running"
    elif action == "stop":
        cur.status = "stopped"
    else:
        cur.speed = speed
    session.flush()
    session.refresh(cur)
    return _out(cur, well)


def sessions(session: Session, limit: int = 20) -> list[ReplaySessionOut]:
    rows = session.execute(
        select(ReplaySession, Well)
        .join(Well, Well.id == ReplaySession.well_id)
        .order_by(ReplaySession.id.desc())
        .limit(limit)
    ).all()
    return [_out(rs, w) for rs, w in rows]


def status(session: Session, heartbeat: str | None) -> StreamStatus:
    hb: dict[str, Any] | None = json.loads(heartbeat) if heartbeat else None
    return StreamStatus(service_alive=hb is not None, heartbeat=hb, sessions=sessions(session))


def _stride(n: int, max_points: int) -> int:
    return max(1, -(-n // max_points))


def window(
    session: Session, well_id: int, minutes: int, max_points: int, thresholds: dict[str, float]
) -> RealtimeWindow:
    well = get_well_or_404(session, well_id)
    rs = _latest_session(session, well_id)
    wb = (
        rs.wellbore_id
        if rs
        else session.scalar(
            select(Wellbore.id).where(Wellbore.well_id == well_id).order_by(Wellbore.id).limit(1)
        )
    )
    last = (
        session.scalar(
            select(RtSample.ts)
            .where(RtSample.wellbore_id == wb)
            .order_by(RtSample.ts.desc())
            .limit(1)
        )
        if wb
        else None
    )
    samples: list[RtSample] = []
    scores: list[RtScore] = []
    latest: dict[str, Any] | None = None
    if last is not None:
        t0 = last - timedelta(minutes=minutes)
        samples = list(
            session.scalars(
                select(RtSample)
                .where(RtSample.wellbore_id == wb, RtSample.ts > t0)
                .order_by(RtSample.ts)
            )
        )
        scores = list(
            session.scalars(
                select(RtScore)
                .where(RtScore.wellbore_id == wb, RtScore.ts > t0)
                .order_by(RtScore.ts)
            )
        )
    step = _stride(len(samples), max_points)
    picked = samples[::step]
    if samples and picked[-1] is not samples[-1]:
        picked.append(samples[-1])
    scored = [s for s in scores if s.scores]
    by_ts = {s.ts: s for s in scores}
    if scores:
        tail = scores[-1]
        latest = {
            "ts": tail.ts.isoformat(),
            "rig_state": tail.rig_state,
            "bit_depth_m": tail.bit_depth_m,
            "formation": tail.formation,
            "indicators": tail.indicators,
            "scores": scored[-1].scores if scored else {},
            "dejavu": next((s.dejavu for s in reversed(scores) if s.dejavu), None),
        }
    types = sorted({t for s in scored for t in s.scores})
    running = rs is not None and rs.status == "running"
    stale = bool(running and rs is not None and rs.updated_at < datetime.now(tz=UTC) - STALE_AFTER)
    return RealtimeWindow(
        well_id=well.id,
        well_name=well.canonical_name,
        wellbore_id=wb,
        synthetic=well.synthetic,
        session=_out(rs, well) if rs else None,
        channels=list(CHANNELS),
        units=UNITS,
        ts=[s.ts for s in picked],
        values={c: [getattr(s, c) for s in picked] for c in CHANNELS},
        rig_state=[by_ts[s.ts].rig_state if s.ts in by_ts else None for s in picked],
        scores_ts=[s.ts for s in scored],
        scores={t: [s.scores.get(t) for s in scored] for t in types},
        thresholds=thresholds,
        latest=latest,
        stale=stale,
    )
