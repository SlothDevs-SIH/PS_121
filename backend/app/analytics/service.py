"""Analytics over the extracted events and the alerts (B5): NPT by group, recurring
problems, alert quality from engineers' feedback. Read-only aggregates; every row keeps
event ids for click-through where it summarises events."""

import statistics
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.schemas.analytics import (
    AlertQuality,
    GroupBy,
    NptBreakdown,
    NptRow,
    Proportion,
    RecurringProblems,
    RecurringRow,
    RepeatInWell,
)
from app.db.models import Event, Field, Formation, Well
from app.db.models.realtime import Alert, AlertFeedback, ReplaySession
from app.ledger.core import posterior
from app.normalise.formations import formation_ids

DT_S = 10


def _events(
    session: Session, event_type: str | None, formation: str | None
) -> list[tuple[Any, ...]]:
    q = (
        select(
            Event.id,
            Event.event_type,
            Formation.name,
            Event.event_date,
            Well.id,
            Well.canonical_name,
            Field.name,
            Event.npt_hours,
            Well.synthetic,
        )
        .join(Well, Well.id == Event.well_id)
        .join(Field, Field.id == Well.field_id)
        .outerjoin(Formation, Formation.id == Event.formation_id)
        .where(Event.status == "active")
    )
    if event_type:
        q = q.where(Event.event_type == event_type)
    if formation:
        q = q.where(Event.formation_id.in_(formation_ids(session, formation)[0]))
    return [tuple(r) for r in session.execute(q)]


def npt(
    session: Session, group_by: GroupBy, event_type: str | None = None, formation: str | None = None
) -> NptBreakdown:
    rows = _events(session, event_type, formation)
    col = {"event_type": 1, "formation": 2, "year": 3, "well": 5, "field": 6}[group_by]
    groups: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for r in rows:
        v = r[col]
        key = str(v.year) if group_by == "year" and v else (str(v) if v else "unknown")
        groups[key].append(r)
    total = sum(r[7] or 0 for r in rows)
    out = []
    for key, rs in groups.items():
        hours = [r[7] for r in rs if r[7] is not None]
        h = sum(hours)
        out.append(
            NptRow(
                key=key,
                events=len(rs),
                wells=len({r[4] for r in rs}),
                npt_hours=round(h, 1),
                share_of_npt=round(h / total, 4) if total else 0.0,
                median_npt_hours=round(statistics.median(hours), 2) if hours else None,
            )
        )
    out.sort(key=lambda r: (-r.npt_hours, r.key))
    return NptBreakdown(
        group_by=group_by,
        rows=out,
        total_events=len(rows),
        total_npt_hours=round(total, 1),
        events_without_npt=sum(1 for r in rows if r[7] is None),
        synthetic=any(r[8] for r in rows),
    )


def recurring(session: Session, min_wells: int = 3) -> RecurringProblems:
    rows = _events(session, None, None)
    by_fm: dict[tuple[str, str], list[tuple[Any, ...]]] = defaultdict(list)
    by_well: dict[tuple[int, str], list[tuple[Any, ...]]] = defaultdict(list)
    for r in rows:
        if r[2]:
            by_fm[(r[1], r[2])].append(r)
        by_well[(r[4], r[1])].append(r)
    across = []
    for (et, fm), rs in by_fm.items():
        wells = {r[4] for r in rs}
        if len(wells) < min_wells:
            continue
        years = [r[3].year for r in rs if r[3]]
        across.append(
            RecurringRow(
                event_type=et,
                formation=fm,
                wells=len(wells),
                events=len(rs),
                npt_hours=round(sum(r[7] or 0 for r in rs), 1),
                first_year=min(years) if years else None,
                last_year=max(years) if years else None,
                event_ids=[r[0] for r in rs][:10],
            )
        )
    across.sort(key=lambda r: (-r.wells, -r.npt_hours))
    within = [
        RepeatInWell(
            well_id=wid,
            well_name=rs[0][5],
            event_type=et,
            events=len(rs),
            npt_hours=round(sum(r[7] or 0 for r in rs), 1),
        )
        for (wid, et), rs in by_well.items()
        if len(rs) >= 2
    ]
    within.sort(key=lambda r: (-r.events, -r.npt_hours, r.well_name))
    return RecurringProblems(
        min_wells=min_wells,
        across_wells=across,
        within_wells=within,
        synthetic=any(r[8] for r in rows),
    )


def _prop(k: int, n: int) -> Proportion:
    if n == 0:
        return Proportion(k=0, n=0, mean=None, ci90_low=None, ci90_high=None)
    m, lo, hi = posterior(k, n)
    return Proportion(k=k, n=n, mean=round(m, 4), ci90_low=round(lo, 4), ci90_high=round(hi, 4))


def alert_quality(session: Session, well_id: int | None = None) -> AlertQuality:
    q = select(Alert)
    if well_id is not None:
        q = q.where(Alert.well_id == well_id)
    alerts = list(session.scalars(q))
    ids = [a.id for a in alerts]
    latest: dict[int, str] = {}
    for alert_id, verdict in session.execute(
        select(AlertFeedback.alert_id, AlertFeedback.verdict)
        .where(AlertFeedback.alert_id.in_(ids or [-1]))
        .order_by(AlertFeedback.id)
    ):
        latest[alert_id] = verdict  # the latest verdict per alert counts
    fb: dict[str, int] = defaultdict(int)
    for v in latest.values():
        fb[v] += 1

    def count(key: str) -> dict[str, int]:
        c: dict[str, int] = defaultdict(int)
        for a in alerts:
            c[str(getattr(a, key))] += 1
        return dict(sorted(c.items()))

    sources: dict[str, int] = defaultdict(int)
    for a in alerts:
        for s in set(a.sources):
            sources[s] += 1
    acked = [a for a in alerts if a.acked_at is not None]
    minutes = [(a.acked_at - a.created_at).total_seconds() / 60 for a in acked if a.acked_at]
    # Every replay run's published rows (samples of an earlier run are replaced when a well is
    # replayed again, but its alerts are kept, so stored samples would undercount the hours).
    rq = select(func.coalesce(func.sum(ReplaySession.position), 0))
    if well_id is not None:
        rq = rq.where(ReplaySession.well_id == well_id)
    hours = float(session.scalar(rq) or 0) * DT_S / 3600
    return AlertQuality(
        alerts=len(alerts),
        by_type=count("event_type"),
        by_source=dict(sorted(sources.items())),
        by_severity=count("severity"),
        by_status=count("status"),
        feedback=dict(sorted(fb.items())),
        precision=_prop(fb["useful"], sum(fb.values())),
        acknowledged=_prop(len(acked), len(alerts)),
        median_minutes_to_ack=round(statistics.median(minutes), 1) if minutes else None,
        data_hours=round(hours, 2),
        alerts_per_12h=round(len(alerts) / hours * 12, 2) if hours else None,
        note=(
            "Precision counts engineers' verdicts (latest per alert), so it covers only alerts "
            "that received feedback. Data hours are the rows published by every replay run "
            "(10 s each), so alerts per 12 h compare like with like across repeated replays."
        ),
    )
