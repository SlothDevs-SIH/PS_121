"""Wells, offsets, trajectories and formations (B1). B2 adds the map bbox / fluid filters,
the AT_FORMATION and CLOSEST_APPROACH offset modes, trajectory-at-depth and survey upload.
The risk profile and the Offset Risk Brief remain skeletons until their phases.
Correlation lives in correlation.py."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.params import NOT_FOUND, InvalidParamsError, check_range, parse_bbox
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
from app.geo import proximity, trajectory_service
from app.geo.service import path_latlon, surface_offsets
from app.normalise import well360
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
    items, total = list_wells(
        session, field, status, q, limit, offset, bbox=parse_bbox(bbox), fluid_type=fluid_type
    )
    return WellList(items=items, total=total)


@router.get(
    "/wells/{well_id}", tags=["wells"], summary="Well 360 summary", response_model=WellDetail
)
def get_well(well_id: int, session: DbSession) -> WellDetail:
    return well360.enrich(session, well_detail(session, well_id))


@router.get(
    "/wells/{well_id}/offsets",
    tags=["wells"],
    summary="Offset wells within a radius",
    response_model=OffsetsOut,
    responses=NOT_FOUND,
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
    well = get_well_or_404(session, well_id)
    radius_m = radius_km * 1000
    if mode is ProximityMode.SURFACE:
        rows = surface_offsets(session, well_id, radius_m)
        return OffsetsOut(
            well_id=well_id,
            mode=mode.value,
            radius_km=radius_km,
            formation=formation,
            distance_label=SURFACE_DISTANCE_LABEL,
            offsets=[OffsetOut.model_validate(r.__dict__) for r in rows],
        )
    if mode is ProximityMode.AT_FORMATION:
        if not formation:
            raise InvalidParamsError("formation", "mode=AT_FORMATION needs formation")
        result = proximity.at_formation(session, well, formation, radius_m)
        label = f"3D distance between entry points into {formation}"
    else:
        result = proximity.closest_approach(session, well, radius_m, tvdss_from_m, tvdss_to_m)
        label = "Closest 3D distance between wellbore paths"
        if tvdss_from_m is not None or tvdss_to_m is not None:
            lo = "top" if tvdss_from_m is None else f"{tvdss_from_m:g} m"
            hi = "TD" if tvdss_to_m is None else f"{tvdss_to_m:g} m"
            label += f" (TVDSS {lo} to {hi})"
    return OffsetsOut(
        well_id=well_id,
        mode=mode.value,
        radius_km=radius_km,
        formation=formation,
        tvdss_from_m=tvdss_from_m,
        tvdss_to_m=tvdss_to_m,
        distance_label=label,
        subject_entry_md_m=result.subject_entry_md_m,
        subject_entry_tvdss_m=result.subject_entry_tvdss_m,
        offsets=[OffsetOut.model_validate(r.__dict__) for r in result.rows],
        excluded=result.excluded,
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
    responses=NOT_FOUND,
)
def get_trajectory_at_depth(
    well_id: int, md_m: Annotated[float, Query(ge=0, le=15000)], session: DbSession
) -> TrajectoryAtDepth:
    """Minimum-curvature interpolation between the bracketing stations; 422 when ``md_m``
    is beyond the last station."""
    return trajectory_service.at_depth(session, get_well_or_404(session, well_id), md_m)


@router.post(
    "/wells/{well_id}/trajectory",
    tags=["wells"],
    summary="Upload survey stations and recompute the trajectory",
    response_model=TrajectoryOut,
    responses=NOT_FOUND,
)
def upload_survey(
    well_id: int, body: Annotated[SurveyUpload, Body()], session: DbSession
) -> TrajectoryOut:
    """Replaces the primary wellbore's stations, recomputes them by minimum curvature,
    rebuilds ``path_geom`` and formation entry points, and clears ``trajectory_assumed``.
    Depth references derived from the trajectory (event, casing, cement and mud TVD/TVDSS)
    are recomputed too."""
    well = get_well_or_404(session, well_id)
    trajectory_service.replace_survey(session, well, body)
    session.commit()
    session.expire_all()
    return get_trajectory(well_id, session)


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
