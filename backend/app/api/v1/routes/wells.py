"""Wells, offsets, trajectories and formations (B1). Correlation, risk profile and the
Offset Risk Brief remain skeletons until their phases."""

from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.schemas.wells import (
    FormationOut,
    OffsetOut,
    OffsetsOut,
    PathPoint,
    StationOut,
    TrajectoryOut,
    WellDetail,
    WellList,
)
from app.core.errors import NOT_IMPLEMENTED, NotFoundError, NotImplementedYetError
from app.db.models import Field, Formation
from app.db.session import get_session
from app.geo.service import path_latlon, surface_offsets
from app.normalise.wells_service import get_well_or_404, list_wells, well_detail

router = APIRouter()
DbSession = Annotated[Session, Depends(get_session)]


class ProximityMode(StrEnum):
    SURFACE = "SURFACE"
    AT_FORMATION = "AT_FORMATION"
    CLOSEST_APPROACH = "CLOSEST_APPROACH"


class Alignment(StrEnum):
    TVDSS = "TVDSS"
    FLATTEN_ON_TOP = "FLATTEN_ON_TOP"
    FORMATION_RELATIVE = "FORMATION_RELATIVE"


@router.get("/wells", tags=["wells"], summary="List and filter wells", response_model=WellList)
def get_wells(
    session: DbSession,
    field: str | None = None,
    status: str | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> WellList:
    items, total = list_wells(session, field, status, q, limit, offset)
    return WellList(items=items, total=total)


@router.get(
    "/wells/{well_id}", tags=["wells"], summary="Well 360 summary", response_model=WellDetail
)
def get_well(well_id: int, session: DbSession) -> WellDetail:
    return well_detail(session, well_id)


@router.get(
    "/wells/{well_id}/offsets",
    tags=["wells"],
    summary="Offset wells within a radius",
    response_model=OffsetsOut,
    responses=NOT_IMPLEMENTED,
)
def get_offsets(
    well_id: int,
    session: DbSession,
    radius_km: Annotated[float, Query(gt=0, le=100)] = 5.0,
    mode: ProximityMode = ProximityMode.SURFACE,
    formation: str | None = None,
) -> OffsetsOut:
    if mode is not ProximityMode.SURFACE:
        raise NotImplementedYetError(f"Offset search, mode {mode.value} (S4)", "B2")
    get_well_or_404(session, well_id)
    rows = surface_offsets(session, well_id, radius_km * 1000)
    return OffsetsOut(
        well_id=well_id,
        mode=mode.value,
        radius_km=radius_km,
        formation=formation,
        offsets=[OffsetOut.model_validate(r.__dict__) for r in rows],
    )


@router.get(
    "/wells/{well_id}/trajectory",
    tags=["wells"],
    summary="Survey stations and 3D path",
    response_model=TrajectoryOut,
)
def get_trajectory(well_id: int, session: DbSession) -> TrajectoryOut:
    well = get_well_or_404(session, well_id)
    if not well.wellbores:
        raise NotFoundError(f"Well {well_id} has no wellbore.", {"well_id": well_id})
    wb = well.wellbores[0]
    field = session.get(Field, well.field_id)
    assert field is not None
    return TrajectoryOut(
        well_id=well.id,
        wellbore_id=wb.id,
        assumed=wb.trajectory_assumed,
        crs_epsg=field.crs_epsg,
        stations=[StationOut.model_validate(s, from_attributes=True) for s in wb.stations],
        path=[PathPoint.model_validate(p) for p in path_latlon(session, wb.id)],
    )


@router.get(
    "/formations", tags=["wells"], summary="Formation dictionary", response_model=list[FormationOut]
)
def get_formations(session: DbSession, basin: str | None = None) -> list[FormationOut]:
    stmt = select(Formation).order_by(Formation.basin, Formation.strat_order)
    if basin:
        stmt = stmt.where(Formation.basin == basin)
    return [FormationOut.model_validate(f, from_attributes=True) for f in session.scalars(stmt)]


@router.get(
    "/wells/{well_id}/risk-profile",
    tags=["risk"],
    summary="Offset prior risk by depth",
    responses=NOT_IMPLEMENTED,
)
def get_risk_profile(
    well_id: int, sigma_km: Annotated[float | None, Query(gt=0, le=50)] = None
) -> None:
    raise NotImplementedYetError("Offset prior risk (S7a)", "B3")


@router.get(
    "/correlation",
    tags=["correlation"],
    summary="Correlation panel data",
    responses=NOT_IMPLEMENTED,
)
def correlation(
    wells: Annotated[list[int], Query(min_length=1, max_length=20)],
    align: Alignment = Alignment.TVDSS,
    top: str | None = None,
) -> None:
    raise NotImplementedYetError("Correlation panel (S6)", "B2")


@router.get(
    "/reports/offset-brief/{well_id}",
    tags=["reports"],
    summary="Offset Risk Brief (PDF)",
    responses=NOT_IMPLEMENTED,
)
def offset_brief(well_id: int) -> None:
    raise NotImplementedYetError("Offset Risk Brief export", "B5")
