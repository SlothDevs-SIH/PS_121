"""Analytics (B5): NPT breakdowns, recurring problems, alert quality."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.analytics import service
from app.api.v1.schemas.analytics import AlertQuality, GroupBy, NptBreakdown, RecurringProblems
from app.core.auth import require
from app.db.session import get_session
from app.db.vocab import EventType

router = APIRouter(tags=["analytics"])
DbSession = Annotated[Session, Depends(get_session)]


@router.get(
    "/analytics/npt",
    summary="NPT by problem, formation, year, well or field",
    response_model=NptBreakdown,
)
def npt(
    session: DbSession,
    group_by: GroupBy = "event_type",
    event_type: EventType | None = None,
    formation: Annotated[str | None, Query(max_length=100)] = None,
) -> NptBreakdown:
    """Events whose NPT was not recorded count as events but add no hours (they are
    reported separately, never as zero)."""
    return service.npt(session, group_by, event_type, formation)


@router.get(
    "/analytics/recurring",
    summary="Problems that recur across wells in one formation, or within one well",
    response_model=RecurringProblems,
)
def recurring(
    session: DbSession, min_wells: Annotated[int, Query(ge=2, le=50)] = 3
) -> RecurringProblems:
    return service.recurring(session, min_wells)


@router.get(
    "/analytics/alerts",
    dependencies=[Depends(require("read_live"))],
    summary="Alert quality: precision from feedback, acknowledgement, alerts per 12 h",
    response_model=AlertQuality,
)
def alerts(session: DbSession, well_id: int | None = None) -> AlertQuality:
    return service.alert_quality(session, well_id)
