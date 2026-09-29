"""Wells, offsets, trajectories and formations (B1). B2 adds the map bbox / fluid filters,
the AT_FORMATION and CLOSEST_APPROACH offset modes, trajectory-at-depth and survey upload
(contract only until the geo engineer lands them). The risk profile and the Offset Risk Brief
remain skeletons until their phases. Correlation moved to correlation.py."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.params import NOT_FOUND, check_range, parse_bbox
from app.api.v1.schemas.wells import (
    FormationOut,
    OffsetOut,
    OffsetsOut,
    PathPoint,
    ProximityMode,
    StationOut,
    SurveyUpload,
    TrajectoryAtDepth,
    TrajectoryOut,
    WellDetail,
    WellList,
)
from app.core.errors import NOT_IMPLEMENTED, NotFoundError, NotImplementedYetError
from app.db.models import Field, Formation
from app.db.session import get_session
from app.db.vocab import FluidType
from app.geo.service import path_latlon, surface_offsets
from app.normalise.wells_service import get_well_or_404, list_wells, well_detail

router = APIRouter()
DbSession = Annotated[Session, Depends(get_session)]

SURFACE_DISTANCE_LABEL = "Surface distance between wellheads"


@router.get("/wells", tags=["wells"], summary="List and filter wells", response_model=WellList)
def get_wells(
    session: DbSession,
    field: str | None = None,
    status: str | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    bbox: Annotated[
        str | None,
        Query(
            max_length=100,
            description="Map viewport 'min_lon,min_lat,max_lon,max_lat' (WGS84 degrees)",
        ),
    ] = None,
    fluid_type: FluidType | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> WellList:
    if parse_bbox(bbox) is not None or fluid_type is not None:
        raise NotImplementedYetError("Well list bbox / fluid_type filters (S3/S4)", "B2")
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
    formation: Annotated[
        str | None, Query(max_length=100, description="AT_FORMATION: formation to compare at")
    ] = None,
    tvdss_from_m: Annotated[
        float | None, Query(description="CLOSEST_APPROACH: TVDSS window start (m)")
    ] = None,
    tvdss_to_m: Annotated[
        float | None, Query(description="CLOSEST_APPROACH: TVDSS window end (m)")
    ] = None,
) -> OffsetsOut:
    """``SURFACE``: wellhead-to-wellhead distance. ``AT_FORMATION`` (needs ``formation``):
    distance between the two wells' entry points into that formation; wells that never
    reach it are listed in ``excluded``. ``CLOSEST_APPROACH``: minimum 3D distance between
    the wellbore paths inside the optional TVDSS window. ``radius_km`` bounds the distance in
    every mode."""
    check_range("tvdss_from_m", tvdss_from_m, "tvdss_to_m", tvdss_to_m)
    if mode is not ProximityMode.SURFACE:
        raise NotImplementedYetError(f"Offset search, mode {mode.value} (S4)", "B2")
    get_well_or_404(session, well_id)
    rows = surface_offsets(session, well_id, radius_km * 1000)
    return OffsetsOut(
        well_id=well_id,
        mode=mode.value,
        radius_km=radius_km,
        formation=formation,
        distance_label=SURFACE_DISTANCE_LABEL,
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
    "/wells/{well_id}/trajectory/at-depth",
    tags=["wells"],
    summary="Interpolated position at a measured depth",
    response_model=TrajectoryAtDepth,
    responses={**NOT_IMPLEMENTED, **NOT_FOUND},
)
def get_trajectory_at_depth(
    well_id: int, md_m: Annotated[float, Query(ge=0, le=15000)]
) -> TrajectoryAtDepth:
    """Minimum-curvature interpolation between the bracketing stations; 422 when ``md_m``
    is beyond the last station."""
    raise NotImplementedYetError("Trajectory at depth (S4)", "B2")


@router.post(
    "/wells/{well_id}/trajectory",
    tags=["wells"],
    summary="Upload survey stations and recompute the trajectory",
    response_model=TrajectoryOut,
    responses={**NOT_IMPLEMENTED, **NOT_FOUND},
)
def upload_survey(well_id: int, body: Annotated[SurveyUpload, Body()]) -> TrajectoryOut:
    """Replaces the primary wellbore's stations, recomputes them by minimum curvature,
    rebuilds ``path_geom`` and formation entry points, and clears ``trajectory_assumed``."""
    raise NotImplementedYetError("Survey upload (S4)", "B2")


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
    "/reports/offset-brief/{well_id}",
    tags=["reports"],
    summary="Offset Risk Brief (PDF)",
    responses=NOT_IMPLEMENTED,
)
def offset_brief(well_id: int) -> None:
    raise NotImplementedYetError("Offset Risk Brief export", "B5")
