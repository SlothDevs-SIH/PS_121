"""Correlation panel (3 alignments) and formation statistics (S6, B2)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.params import NOT_FOUND, InvalidParamsError, RadiusKm
from app.api.v1.schemas.correlation import Alignment, CorrelationPanel, FormationStats
from app.correlation import service
from app.db.session import get_session

router = APIRouter(tags=["correlation"], responses=NOT_FOUND)
DbSession = Annotated[Session, Depends(get_session)]

MAX_PANEL_WELLS = 20
MAX_STATS_WELLS = 100


@router.get("/correlation", summary="Correlation panel data", response_model=CorrelationPanel)
def correlation(
    session: DbSession,
    wells: Annotated[list[int], Query(min_length=1, max_length=MAX_PANEL_WELLS)],
    align: Alignment = Alignment.TVDSS,
    top: Annotated[
        str | None, Query(max_length=100, description="Formation to flatten on (FLATTEN_ON_TOP)")
    ] = None,
) -> CorrelationPanel:
    """One column per well, in the order given, with formation / casing / mud / cement /
    event tracks on a shared aligned axis. Unknown well ids answer 404."""
    if align is Alignment.FLATTEN_ON_TOP and not top:
        raise InvalidParamsError("top", "align=FLATTEN_ON_TOP needs top (a formation name)")
    return service.panel(session, list(dict.fromkeys(wells)), align, top)


@router.get(
    "/correlation/formation-stats",
    summary="Per-formation offset statistics",
    response_model=FormationStats,
)
def formation_stats(
    session: DbSession,
    wells: Annotated[list[int] | None, Query(max_length=MAX_STATS_WELLS)] = None,
    well_id: int | None = None,
    radius_km: RadiusKm = None,
) -> FormationStats:
    """Either an explicit ``wells`` list, or ``well_id`` plus ``radius_km`` (default 5 km):
    the well and its surface offsets. Rows are in stratigraphic order."""
    if bool(wells) == (well_id is not None):
        raise InvalidParamsError("wells", "give either wells or well_id (+ radius_km), not both")
    if radius_km is not None and well_id is None:
        raise InvalidParamsError("radius_km", "radius_km needs well_id (the circle's centre)")
    return service.formation_stats(session, wells, well_id, radius_km)
