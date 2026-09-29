"""Drilling events: search, detail, manual entry, verification, per-well timeline (S2, B2).

Handlers validate cross-parameter rules and delegate to app.extract.events_service.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.v1.params import (
    NOT_FOUND,
    Cursor,
    Limit,
    RadiusKm,
    check_range,
    require_well_for_radius,
)
from app.api.v1.schemas.events import (
    EventCreate,
    EventDetail,
    EventPage,
    EventTimeline,
    EventVerify,
)
from app.core.audit import audit
from app.core.auth import CurrentUser, get_current_user, require
from app.db.session import get_session
from app.db.vocab import EventType
from app.extract import events_service

router = APIRouter(tags=["events"])
DbSession = Annotated[Session, Depends(get_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]


@router.get("/events", summary="Search drilling events", response_model=EventPage)
def list_events(
    session: DbSession,
    event_type: Annotated[
        list[EventType] | None, Query(description="Repeat to match any of several types")
    ] = None,
    formation: Annotated[str | None, Query(max_length=100)] = None,
    well_id: int | None = None,
    radius_km: RadiusKm = None,
    tvdss_from_m: float | None = None,
    tvdss_to_m: float | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    verified: Annotated[bool | None, Query(description="Only verified / unverified")] = None,
    min_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
    limit: Limit = 50,
    cursor: Cursor = None,
) -> EventPage:
    """Active events matching every given filter, ordered by (well name, md_m, id).

    ``formation`` matches a formation name or synonym (case-insensitive). With ``radius_km``
    the events of ``well_id`` *and* of every well whose surface location lies within the
    radius are returned; without it, only ``well_id``'s. Rejected events are never listed.
    """
    require_well_for_radius(well_id, radius_km)
    check_range("tvdss_from_m", tvdss_from_m, "tvdss_to_m", tvdss_to_m)
    check_range("date_from", date_from, "date_to", date_to)
    return events_service.list_events(
        session,
        event_types=list(event_type) if event_type else None,
        formation=formation,
        well_id=well_id,
        radius_km=radius_km,
        tvdss_from_m=tvdss_from_m,
        tvdss_to_m=tvdss_to_m,
        date_from=date_from,
        date_to=date_to,
        verified=verified,
        min_confidence=min_confidence,
        limit=limit,
        cursor=cursor,
    )


@router.get(
    "/events/{event_id}",
    summary="Event detail with mitigations, evidence and lesson card",
    response_model=EventDetail,
    responses=NOT_FOUND,
)
def get_event(event_id: int, session: DbSession) -> EventDetail:
    """One event (active or rejected) with its mitigations in the order tried."""
    return events_service.event_detail(session, event_id)


@router.post(
    "/events",
    dependencies=[Depends(require("review"))],
    summary="Record an event manually",
    response_model=EventDetail,
    status_code=status.HTTP_201_CREATED,
    responses=NOT_FOUND,
)
def create_event(body: EventCreate, session: DbSession, user: User) -> EventDetail:
    """Stores the event with ``source='manual'``, ``verified=false``; depth references
    (``tvd_m``/``tvdss_m``) and the formation are derived from ``md_m`` when not given.
    404 if the well does not exist; 422 if evidence spans are not on the cited page."""
    detail = events_service.create_event(session, body)
    audit(session, user, "event_create", "event", detail.id, well_id=body.well_id)
    session.commit()
    return detail


@router.patch(
    "/events/{event_id}/verify",
    dependencies=[Depends(require("review"))],
    summary="Verify, un-verify or reject an event",
    response_model=EventDetail,
    responses=NOT_FOUND,
)
def verify_event(
    event_id: int, body: Annotated[EventVerify, Body()], session: DbSession, user: User
) -> EventDetail:
    """Sets ``verified``/``verified_by``/``verified_at`` (and ``status`` when given) and
    closes any pending review items for the event."""
    detail = events_service.verify_event(
        session,
        event_id,
        verified=body.verified,
        status=body.status,
        note=body.note,
        user=user.user_id,
    )
    audit(session, user, "event_verify", "event", event_id, verified=body.verified)
    session.commit()
    return detail


@router.get(
    "/wells/{well_id}/events/timeline",
    summary="Chronological event list for one well",
    response_model=EventTimeline,
    responses=NOT_FOUND,
)
def get_event_timeline(well_id: int, session: DbSession) -> EventTimeline:
    """Active events of the well plus its DDR NPT lines, for the Well 360 Events tab."""
    return events_service.timeline(session, well_id)
