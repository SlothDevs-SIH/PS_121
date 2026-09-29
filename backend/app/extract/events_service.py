"""Event queries and edits behind the /events API (S2)."""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session, selectinload

from app.api.v1.params import InvalidParamsError, decode_cursor, encode_cursor
from app.api.v1.schemas.common import EvidenceRefIn
from app.api.v1.schemas.events import (
    DdrOperationOut,
    EventCreate,
    EventDetail,
    EventPage,
    EventParams,
    EventSummary,
    EventTimeline,
    LessonCardContent,
    MitigationOut,
)
from app.core.errors import NotFoundError
from app.db.models import (
    DdrOperation,
    Event,
    EventEvidence,
    Formation,
    Mitigation,
    Page,
    ReviewItem,
    TextSpan,
    Well,
    Wellbore,
)
from app.extract.evidence import event_evidence_refs, record_evidence
from app.extract.service import WellContext
from app.geo.service import surface_offsets
from app.normalise.formations import formation_ids, formation_names
from app.normalise.wells_service import get_well_or_404
from app.search.service import refresh_lesson_cards

_NO_DEPTH = 1e9  # sort key for events without a depth (listed last within their well)


def _summaries(session: Session, events: list[Event]) -> list[EventSummary]:
    if not events:
        return []
    wells = {
        w.id: w
        for w in session.scalars(select(Well).where(Well.id.in_({e.well_id for e in events})))
    }
    names = formation_names(session)
    evidence = event_evidence_refs(session, [e.id for e in events])
    return [
        EventSummary(
            id=e.id,
            well_id=e.well_id,
            well_name=wells[e.well_id].canonical_name,
            wellbore_id=e.wellbore_id,
            synthetic=wells[e.well_id].synthetic,
            event_type=e.event_type,
            subtype=e.subtype,
            severity=e.severity,
            event_date=e.event_date,
            t_start=e.t_start,
            t_end=e.t_end,
            md_m=e.md_m,
            tvd_m=e.tvd_m,
            tvdss_m=e.tvdss_m,
            formation_id=e.formation_id,
            formation=names.get(e.formation_id) if e.formation_id else None,
            hole_size_in=e.hole_size_in,
            mw_sg=e.mw_sg,
            npt_hours=e.npt_hours,
            resolved=e.resolved,
            source=e.source,
            status=e.status,
            confidence=e.confidence,
            verified=e.verified,
            evidence=evidence.get(e.id, []),
        )
        for e in events
    ]


def list_events(
    session: Session,
    *,
    event_types: list[str] | None,
    formation: str | None,
    well_id: int | None,
    radius_km: float | None,
    tvdss_from_m: float | None,
    tvdss_to_m: float | None,
    date_from: date | None,
    date_to: date | None,
    verified: bool | None,
    min_confidence: float | None,
    limit: int,
    cursor: str | None,
) -> EventPage:
    after = decode_cursor(cursor, 3)
    md_key = func.coalesce(Event.md_m, _NO_DEPTH)
    q = select(Event, Well.canonical_name).join(Well, Well.id == Event.well_id)
    q = q.where(Event.status == "active")
    if event_types:
        q = q.where(Event.event_type.in_(event_types))
    if formation:
        q = q.where(Event.formation_id.in_(formation_ids(session, formation)[0]))
    if well_id is not None:
        get_well_or_404(session, well_id)
        wells = [well_id]
        if radius_km:
            wells += [o.well_id for o in surface_offsets(session, well_id, radius_km * 1000)]
        q = q.where(Event.well_id.in_(wells))
    if tvdss_from_m is not None:
        q = q.where(Event.tvdss_m >= tvdss_from_m)
    if tvdss_to_m is not None:
        q = q.where(Event.tvdss_m <= tvdss_to_m)
    if date_from is not None:
        q = q.where(Event.event_date >= date_from)
    if date_to is not None:
        q = q.where(Event.event_date <= date_to)
    if verified is not None:
        q = q.where(Event.verified.is_(verified))
    if min_confidence is not None:
        q = q.where(Event.confidence >= min_confidence)
    if after is not None:
        q = q.where(tuple_(Well.canonical_name, md_key, Event.id) > tuple_(*after))
    rows = session.execute(q.order_by(Well.canonical_name, md_key, Event.id).limit(limit + 1)).all()
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last_event, last_name = page[-1]
        next_cursor = encode_cursor(
            [
                last_name,
                last_event.md_m if last_event.md_m is not None else _NO_DEPTH,
                last_event.id,
            ]
        )
    return EventPage(items=_summaries(session, [e for e, _ in page]), next_cursor=next_cursor)


def _load(session: Session, event_id: int) -> Event:
    ev = session.scalar(
        select(Event).where(Event.id == event_id).options(selectinload(Event.mitigations))
    )
    if ev is None:
        raise NotFoundError(f"Event {event_id} not found.", {"event_id": event_id})
    return ev


def event_detail(session: Session, event_id: int) -> EventDetail:
    ev = _load(session, event_id)
    (summary,) = _summaries(session, [ev])
    mits = sorted(ev.mitigations, key=lambda m: m.seq)
    mit_evidence = record_evidence(session, [(m.document_id, m.page_no, m.span_ids) for m in mits])
    return EventDetail(
        **summary.model_dump(),
        params=EventParams.model_validate(ev.params or {}),
        cause_text=ev.cause_text,
        description=ev.description,
        lesson_card=LessonCardContent.model_validate(ev.lesson_card) if ev.lesson_card else None,
        mitigations=[
            MitigationOut(
                id=m.id,
                seq=m.seq,
                action_code=m.action_code,
                action_text=m.action_text,
                t_start=m.t_start,
                outcome=m.outcome,
                npt_hours_after=m.npt_hours_after,
                volume_lost_m3=m.volume_lost_m3,
                recurrence=m.recurrence,
                confidence=m.confidence,
                verified=m.verified,
                evidence=ev_refs,
            )
            for m, ev_refs in zip(mits, mit_evidence, strict=True)
        ],
        verified_by=ev.verified_by,
        verified_at=ev.verified_at,
        created_at=ev.created_at,
        updated_at=ev.updated_at,
    )


# ─── Manual entry ──────────────────────────────────────────────────────────────────────────


def _checked_spans(session: Session, ref: EvidenceRefIn, param: str) -> list[int]:
    """Span ids of the cited page (all of them when none are named); 422 if any named span
    is not on that page of that document."""
    on_page = set(
        session.scalars(
            select(TextSpan.id)
            .join(Page, Page.id == TextSpan.page_id)
            .where(Page.document_id == ref.document_id, Page.page_no == ref.page_no)
        )
    )
    if not on_page:
        raise InvalidParamsError(
            param, f"document {ref.document_id} has no page {ref.page_no} with text"
        )
    wanted = set(ref.span_ids) or on_page
    if not wanted <= on_page:
        raise InvalidParamsError(param, f"spans {sorted(wanted - on_page)} are not on that page")
    return sorted(wanted)


def create_event(session: Session, body: EventCreate) -> EventDetail:
    well = get_well_or_404(session, body.well_id)
    if body.wellbore_id is not None and not session.scalar(
        select(func.count()).where(Wellbore.id == body.wellbore_id, Wellbore.well_id == well.id)
    ):
        raise InvalidParamsError("wellbore_id", "wellbore does not belong to the well")
    if body.formation_id is not None and session.get(Formation, body.formation_id) is None:
        raise InvalidParamsError("formation_id", "unknown formation")
    ctx = WellContext.load(session, well.id)
    tvd, tvdss = ctx.depth_refs(body.md_m)
    ev = Event(
        well_id=well.id,
        wellbore_id=body.wellbore_id
        if body.wellbore_id is not None
        else (ctx.wellbore_id if ctx.single_wellbore else None),
        event_type=body.event_type,
        subtype=body.subtype,
        severity=body.severity,
        event_date=body.event_date or (body.t_start.date() if body.t_start else None),
        t_start=body.t_start,
        t_end=body.t_end,
        md_m=body.md_m,
        tvd_m=tvd,
        tvdss_m=tvdss,
        formation_id=body.formation_id or ctx.formation_at(body.md_m),
        hole_size_in=body.hole_size_in,
        mw_sg=body.mw_sg,
        params=body.params.model_dump(exclude_none=True),
        cause_text=body.cause_text,
        description=body.description,
        npt_hours=body.npt_hours,
        resolved=body.resolved,
        confidence=1.0,  # entered by a person; still unverified until a reviewer agrees
        verified=False,
        source="manual",
        status="active",
    )
    session.add(ev)
    session.flush()
    for k, ref in enumerate(body.evidence):
        for span_id in _checked_spans(session, ref, f"evidence.{k}"):
            ev.evidence.append(
                EventEvidence(
                    span_id=span_id,
                    document_id=ref.document_id,
                    page_no=ref.page_no,
                    role="primary",
                )
            )
    for seq, m in enumerate(body.mitigations, start=1):
        if len({(r.document_id, r.page_no) for r in m.evidence}) > 1:
            raise InvalidParamsError(
                f"mitigations.{seq - 1}.evidence", "a mitigation cites one document page"
            )
        first = m.evidence[0] if m.evidence else None
        spans = [
            s for r in m.evidence for s in _checked_spans(session, r, f"mitigations.{seq - 1}")
        ]
        ev.mitigations.append(
            Mitigation(
                seq=seq,
                action_code=m.action_code,
                action_text=m.action_text,
                t_start=m.t_start,
                outcome=m.outcome,
                npt_hours_after=m.npt_hours_after,
                volume_lost_m3=m.volume_lost_m3,
                recurrence=m.recurrence,
                document_id=first.document_id if first else None,
                page_no=first.page_no if first else None,
                span_ids=sorted(set(spans)),
                confidence=1.0,
            )
        )
    session.flush()
    refresh_lesson_cards(session, [ev.id])
    return event_detail(session, ev.id)


# ─── Verification ──────────────────────────────────────────────────────────────────────────


def close_reviews(session: Session, event: Event, status: str, user: str) -> None:
    now = datetime.now(tz=UTC)
    mit_ids = [m.id for m in event.mitigations]
    items = session.scalars(
        select(ReviewItem).where(
            ReviewItem.status == "pending",
            ((ReviewItem.kind == "event") & (ReviewItem.target_id == event.id))
            | ((ReviewItem.kind == "mitigation") & ReviewItem.target_id.in_(mit_ids or [-1])),
        )
    )
    for item in items:
        item.status, item.decided_by, item.decided_at = status, user, now


def verify_event(
    session: Session,
    event_id: int,
    *,
    verified: bool,
    status: str | None,
    note: str | None,
    user: str,
) -> EventDetail:
    ev = _load(session, event_id)
    now = datetime.now(tz=UTC)
    ev.verified = verified
    ev.verified_by = user if verified else None
    ev.verified_at = now if verified else None
    if status is not None:
        ev.status = status
    if verified:
        for m in ev.mitigations:
            m.verified = True
    if status == "rejected":
        close_reviews(session, ev, "rejected", user)
    elif verified:
        close_reviews(session, ev, "accepted", user)
    session.flush()
    return event_detail(session, ev.id)


# ─── Timeline ──────────────────────────────────────────────────────────────────────────────


def timeline(session: Session, well_id: int) -> EventTimeline:
    well = get_well_or_404(session, well_id)
    events = list(
        session.scalars(
            select(Event)
            .where(Event.well_id == well.id, Event.status == "active")
            .order_by(
                Event.event_date.asc().nulls_last(),
                Event.t_start.asc().nulls_last(),
                Event.md_m.asc().nulls_last(),
                Event.id,
            )
        )
    )
    ops = list(
        session.scalars(
            select(DdrOperation)
            .join(Wellbore, Wellbore.id == DdrOperation.wellbore_id)
            .where(Wellbore.well_id == well.id, DdrOperation.is_npt.is_(True))
            .order_by(DdrOperation.t_from.asc().nulls_last(), DdrOperation.id)
        )
    )
    op_evidence = record_evidence(session, [(o.document_id, o.page_no, o.span_ids) for o in ops])
    counts: dict[str, int] = {}
    for e in events:
        counts[e.event_type] = counts.get(e.event_type, 0) + 1
    npts = [e.npt_hours for e in events if e.npt_hours is not None]
    return EventTimeline(
        well_id=well.id,
        well_name=well.canonical_name,
        synthetic=well.synthetic,
        spud_date=well.spud_date,
        completion_date=well.completion_date,
        td_md_m=well.td_md_m,
        events=_summaries(session, events),
        npt_operations=[
            DdrOperationOut(
                id=o.id,
                document_id=o.document_id,
                page_no=o.page_no,
                report_date=o.report_date,
                t_from=o.t_from,
                t_to=o.t_to,
                hours=o.hours,
                md_m=o.md_m,
                activity_code=o.activity_code,
                description=o.description,
                is_npt=o.is_npt,
                npt_category=o.npt_category,
                event_id=o.event_id,
                evidence=refs,
            )
            for o, refs in zip(ops, op_evidence, strict=True)
        ],
        counts_by_type=counts,
        total_npt_hours=round(sum(npts), 1) if npts else None,
    )


def event_counts_by_type(session: Session, well_id: int) -> dict[str, int]:
    rows = session.execute(
        select(Event.event_type, func.count())
        .where(Event.well_id == well_id, Event.status == "active")
        .group_by(Event.event_type)
    ).all()
    return {str(t): int(n) for t, n in rows}


def recent_events(session: Session, well_id: int, n: int = 5) -> list[EventSummary]:
    events = list(
        session.scalars(
            select(Event)
            .where(Event.well_id == well_id, Event.status == "active")
            .order_by(Event.event_date.desc().nulls_last(), Event.id.desc())
            .limit(n)
        )
    )
    return _summaries(session, events)


def summaries(session: Session, events: list[Event]) -> list[EventSummary]:
    return _summaries(session, events)


def as_dict(ev: Event) -> dict[str, Any]:
    return {c.name: getattr(ev, c.name) for c in Event.__table__.columns}
