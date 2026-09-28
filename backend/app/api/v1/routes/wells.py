"""Skeleton routes for wells, offsets, trajectories, correlation and risk profiles."""

from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.errors import NOT_IMPLEMENTED, NotImplementedYetError

router = APIRouter(responses=NOT_IMPLEMENTED)


class ProximityMode(StrEnum):
    SURFACE = "SURFACE"
    AT_FORMATION = "AT_FORMATION"
    CLOSEST_APPROACH = "CLOSEST_APPROACH"


class Alignment(StrEnum):
    TVDSS = "TVDSS"
    FLATTEN_ON_TOP = "FLATTEN_ON_TOP"
    FORMATION_RELATIVE = "FORMATION_RELATIVE"


@router.get("/wells", tags=["wells"], summary="List and filter wells")
def list_wells(field: str | None = None, status: str | None = None) -> None:
    raise NotImplementedYetError("Well list (S3)", "B1")


@router.get("/wells/{well_id}", tags=["wells"], summary="Well 360 summary")
def get_well(well_id: int) -> None:
    raise NotImplementedYetError("Well 360 summary", "B2")


@router.get("/wells/{well_id}/offsets", tags=["wells"], summary="Offset wells within a radius")
def get_offsets(
    well_id: int,
    radius_km: Annotated[float, Query(gt=0, le=100)] = 5.0,
    mode: ProximityMode = ProximityMode.SURFACE,
    formation: str | None = None,
) -> None:
    raise NotImplementedYetError(f"Offset search, mode {mode.value} (S4)", "B1")


@router.get("/wells/{well_id}/trajectory", tags=["wells"], summary="Survey stations and 3D path")
def get_trajectory(well_id: int) -> None:
    raise NotImplementedYetError("Trajectory (S4)", "B1")


@router.get("/wells/{well_id}/risk-profile", tags=["risk"], summary="Offset prior risk by depth")
def get_risk_profile(
    well_id: int, sigma_km: Annotated[float | None, Query(gt=0, le=50)] = None
) -> None:
    raise NotImplementedYetError("Offset prior risk (S7a)", "B3")


@router.get("/correlation", tags=["correlation"], summary="Correlation panel data")
def correlation(
    wells: Annotated[list[int], Query(min_length=1, max_length=20)],
    align: Alignment = Alignment.TVDSS,
    top: str | None = None,
) -> None:
    raise NotImplementedYetError("Correlation panel (S6)", "B2")


@router.get("/reports/offset-brief/{well_id}", tags=["reports"], summary="Offset Risk Brief (PDF)")
def offset_brief(well_id: int) -> None:
    raise NotImplementedYetError("Offset Risk Brief export", "B5")
