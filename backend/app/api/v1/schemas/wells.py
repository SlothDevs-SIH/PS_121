"""Response models for wells, trajectories, offsets and formations (B1)."""

from datetime import date

from pydantic import BaseModel, Field


class WellSummary(BaseModel):
    id: int
    name: str
    field: str
    status: str
    well_type: str | None
    profile: str | None
    lat: float
    lon: float
    td_md_m: float | None
    spud_date: date | None
    synthetic: bool
    document_count: int


class WellList(BaseModel):
    items: list[WellSummary]
    total: int


class FormationTopOut(BaseModel):
    formation: str
    strat_order: int
    top_md_m: float
    top_tvd_m: float
    top_tvdss_m: float


class QualityCheck(BaseModel):
    name: str
    ok: bool
    detail: str


class DataQuality(BaseModel):
    score: float = Field(ge=0, le=1)
    checks: list[QualityCheck]


class WellDetail(WellSummary):
    aliases: list[str]
    rkb_elev_m: float | None
    gl_elev_m: float | None
    datum_assumed: bool
    completion_date: date | None
    rig_name: str | None
    units_system: str | None
    trajectory_assumed: bool
    crs_epsg: int
    formation_tops: list[FormationTopOut]
    data_quality: DataQuality


class StationOut(BaseModel):
    md_m: float
    inc_deg: float
    azi_deg: float
    tvd_m: float
    tvdss_m: float
    north_m: float
    east_m: float
    dls_deg_30m: float


class PathPoint(BaseModel):
    lat: float
    lon: float
    tvdss_m: float


class TrajectoryOut(BaseModel):
    well_id: int
    wellbore_id: int
    assumed: bool
    crs_epsg: int
    stations: list[StationOut]
    path: list[PathPoint]


class OffsetOut(BaseModel):
    well_id: int
    name: str
    status: str
    well_type: str | None
    lat: float
    lon: float
    td_md_m: float | None
    synthetic: bool
    distance_m: float
    bearing_deg: float | None


class OffsetsOut(BaseModel):
    well_id: int
    mode: str
    radius_km: float
    formation: str | None
    offsets: list[OffsetOut]


class FormationOut(BaseModel):
    id: int
    basin: str
    name: str
    synonyms: list[str]
    strat_order: int
    lithology: str | None
