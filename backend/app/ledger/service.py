"""Ledger over the database: select the events in scope, derive outcomes, summarise."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.v1.schemas.common import EvidenceRef
from app.api.v1.schemas.knowledge import (
    LedgerCase,
    LedgerEntry,
    LedgerResponse,
    LedgerScope,
    SeverityStratum,
)
from app.db.models import Event, Formation, Mitigation, Well
from app.extract.evidence import record_evidence
from app.geo.service import surface_offsets
from app.ledger import core
from app.normalise.formations import formation_ids, formation_names
from app.normalise.wells_service import get_well_or_404

MAX_CASES = 25


def ledger(
    session: Session,
    *,
    event_type: str,
    formation: str | None = None,
    basin: str | None = None,
    well_id: int | None = None,
    radius_km: float | None = None,
    severity: str | None = None,
    min_n: int = core.MIN_N,
) -> LedgerResponse:
    q = (
        select(Event)
        .where(Event.status == "active", Event.event_type == event_type)
        .options(selectinload(Event.mitigations))
    )
    fm_name = None
    if formation:
        ids, _ = formation_ids(session, formation)
        q = q.where(Event.formation_id.in_(ids))
        fm_name = formation_names(session).get(ids[0])
    if basin:
        q = q.where(
            Event.formation_id.in_(select(Formation.id).where(Formation.basin.ilike(basin)))
        )
    if well_id is not None:
        get_well_or_404(session, well_id)
        in_scope = [well_id]
        if radius_km:
            in_scope += [o.well_id for o in surface_offsets(session, well_id, radius_km * 1000)]
        q = q.where(Event.well_id.in_(in_scope))
    if severity:
        q = q.where(Event.severity == severity)
    events = list(session.scalars(q))

    # Recurrence is judged against every active event of the type in those wells.
    peers = list(
        session.scalars(
            select(Event).where(
                Event.status == "active",
                Event.event_type == event_type,
                Event.well_id.in_({e.well_id for e in events} or {-1}),
            )
        )
    )
    lite = [
        core.EventLite(
            p.id,
            p.well_id,
            p.event_type,
            p.tvdss_m,
            p.event_date.toordinal() if p.event_date else None,
        )
        for p in peers
    ]
    by_id = {x.id: x for x in lite}
    wells = {
        w.id: w
        for w in session.scalars(
            select(Well).where(Well.id.in_({e.well_id for e in events} or {-1}))
        )
    }
    names = formation_names(session)

    uses: list[core.UseRecord] = []
    pairs: list[tuple[Event, Mitigation]] = []
    for ev in events:
        again = core.recurred(by_id[ev.id], lite) if ev.id in by_id else False
        for m in ev.mitigations:
            # A success followed by recurrence can only be the event's last action.
            uses.append(
                core.UseRecord(
                    action_code=m.action_code,
                    recorded_outcome=m.outcome,
                    seq=m.seq,
                    recurred=again and m.outcome == "success",
                    severity=ev.severity,
                    npt_hours_after=m.npt_hours_after,
                    volume_lost_m3=m.volume_lost_m3,
                    key=len(pairs),
                )
            )
            pairs.append((ev, m))
    summaries = core.summarise(uses)
    ranked, rest = core.rank(summaries, min_n)

    def entry(s: core.Summary) -> LedgerEntry:
        cases = sorted(s.uses, key=lambda u: (u.outcome != "success", u.seq))[:MAX_CASES]
        refs = record_evidence(
            session,
            [(m.document_id, m.page_no, m.span_ids) for _, m in (pairs[u.key] for u in cases)],
        )
        return LedgerEntry(
            action_code=s.action_code,
            action_label=core.label(s.action_code),
            n=s.n,
            successes=s.successes,
            partial=s.partial,
            failures=s.failures,
            unknown=s.unknown,
            first_choice=s.first_choice,
            success_rate=round(s.success_rate, 4) if s.success_rate is not None else None,
            posterior_mean=round(s.posterior_mean, 4) if s.posterior_mean is not None else None,
            ci90_low=round(s.ci90_low, 4) if s.ci90_low is not None else None,
            ci90_high=round(s.ci90_high, 4) if s.ci90_high is not None else None,
            median_npt_hours=s.median_npt_hours,
            median_volume_lost_m3=s.median_volume_lost_m3,
            by_severity=[
                SeverityStratum(severity=k, n=v[0], successes=v[1])
                for k, v in sorted(s.by_severity.items())
            ],
            summary=s.summary,
            cases=[
                _case(u, pairs[u.key], wells, names, r) for u, r in zip(cases, refs, strict=True)
            ],
        )

    return LedgerResponse(
        event_type=event_type,
        formation=fm_name,
        basin=basin,
        well_id=well_id,
        radius_km=radius_km,
        min_n=min_n,
        outcome_rule=core.OUTCOME_RULE,
        caveat=core.CAVEAT,
        scope=LedgerScope(
            wells=len({e.well_id for e in events}),
            events=len(events),
            mitigations=len(uses),
            unknown_outcomes=sum(u.outcome == "unknown" for u in uses),
        ),
        ranked=[entry(s) for s in ranked],
        insufficient=[entry(s) for s in rest],
        synthetic=any(w.synthetic for w in wells.values()),
    )


def _case(
    u: core.UseRecord,
    pair: tuple[Event, Mitigation],
    wells: dict[int, Well],
    names: dict[int, str],
    evidence: list[EvidenceRef],
) -> LedgerCase:
    ev, m = pair
    w = wells[ev.well_id]
    return LedgerCase(
        event_id=ev.id,
        mitigation_id=m.id,
        well_id=ev.well_id,
        well_name=w.canonical_name,
        synthetic=w.synthetic,
        event_date=ev.event_date.isoformat() if ev.event_date else None,
        formation=names.get(ev.formation_id) if ev.formation_id else None,
        severity=u.severity,
        seq=u.seq,
        outcome=u.outcome,
        recorded_outcome=u.recorded_outcome,
        recurred=u.recurred,
        npt_hours_after=u.npt_hours_after,
        verified=m.verified,
        evidence=evidence,
    )
