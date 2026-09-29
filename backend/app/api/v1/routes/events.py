"""Drilling events: search, detail, manual entry, verification, per-well timeline (S2, B2).

Contract only in this revision: every handler validates its inputs and raises
NotImplementedYetError; the extract/search engineers replace the raises with service calls.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Body, Query, status

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
from app.core.errors import NOT_IMPLEMENTED, NotImplementedYetError
from app.db.vocab import EventType

router = APIRouter(tags=["events"], responses=NOT_IMPLEMENTED)


@router.get("/events", summary="Search drilling events", response_model=EventPage)
def list_events(
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
    raise NotImplementedYetError("Event search (S2/S5)", "B2")


@router.get(
    "/events/{event_id}",
    summary="Event detail with mitigations, evidence and lesson card",
    response_model=EventDetail,
    responses=NOT_FOUND,
)
def get_event(event_id: int) -> EventDetail:
    """One event (active or rejected) with its mitigations in the order tried."""
    raise NotImplementedYetError("Event detail (S2)", "B2")


@router.post(
    "/events",
    summary="Record an event manually",
    response_model=EventDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_event(body: EventCreate) -> EventDetail:
    """Stores the event with ``source='manual'``, ``verified=false``; depth references
    (``tvd_m``/``tvdss_m``) and the formation are derived from ``md_m`` when not given.
    404 if the well does not exist; 422 if evidence spans are not on the cited page."""
    raise NotImplementedYetError("Manual event entry (S2)", "B2")


@router.patch(
    "/events/{event_id}/verify",
    summary="Verify, un-verify or reject an event",
    response_model=EventDetail,
    responses=NOT_FOUND,
)
def verify_event(event_id: int, body: Annotated[EventVerify, Body()]) -> EventDetail:
    """Sets ``verified``/``verified_by``/``verified_at`` (and ``status`` when given) and
    closes any pending review items for the event."""
    raise NotImplementedYetError("Event verification (S2)", "B2")


@router.get(
    "/wells/{well_id}/events/timeline",
    summary="Chronological event list for one well",
    response_model=EventTimeline,
    responses=NOT_FOUND,
)
def get_event_timeline(well_id: int) -> EventTimeline:
    """Active events of the well plus its DDR NPT lines, for the Well 360 Events tab."""
    raise NotImplementedYetError("Event timeline (S2)", "B2")
