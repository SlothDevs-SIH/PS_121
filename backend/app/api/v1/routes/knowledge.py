"""Mitigation Effectiveness Ledger (S8, USP 2), built in B3."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.params import NOT_FOUND, RadiusKm, require_well_for_radius
from app.api.v1.schemas.knowledge import LedgerResponse
from app.core.auth import require
from app.db.session import get_session
from app.db.vocab import EventType, Severity
from app.ledger import core
from app.ledger.service import ledger as build_ledger

router = APIRouter()
DbSession = Annotated[Session, Depends(get_session)]


@router.get(
    "/ledger",
    dependencies=[Depends(require("read_risk"))],
    tags=["ledger"],
    summary="Mitigation effectiveness ranking (USP 2)",
    response_model=LedgerResponse,
    responses=NOT_FOUND,
)
def ledger(
    session: DbSession,
    event_type: EventType,
    formation: Annotated[str | None, Query(max_length=100)] = None,
    basin: Annotated[str | None, Query(max_length=100)] = None,
    well_id: int | None = None,
    radius_km: RadiusKm = None,
    severity: Severity | None = None,
    min_n: Annotated[int, Query(ge=1, le=50, description="Rank only with ≥ min_n outcomes")] = (
        core.MIN_N
    ),
) -> LedgerResponse:
    """Actions against ``event_type`` ranked by recorded outcomes: Beta(1,1) posterior mean
    and 90% credible interval per action, ranked only with at least ``min_n`` known
    outcomes; the rest are listed as insufficient evidence with their cases. Scope with a
    formation (name or synonym), a basin, or ``well_id`` + ``radius_km``; ``severity``
    stratifies. Observational: associated with, not caused by."""
    require_well_for_radius(well_id, radius_km)
    return build_ledger(
        session,
        event_type=event_type,
        formation=formation,
        basin=basin,
        well_id=well_id,
        radius_km=radius_km,
        severity=severity,
        min_n=min_n,
    )
