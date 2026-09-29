"""Response models for wells, trajectories, offsets and formations (B1), with the B2 Well 360
enrichment (casing, cement, mud, events, documents, lessons), proximity-mode fields,
trajectory-at-depth and survey upload. B2 fields have defaults so B1 code keeps working."""

from datetime import date
from enum import StrEnum
from itertools import pairwise

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.api.v1.schemas.common import ExcludedWell, Extracted, ResponseModel
from app.api.v1.schemas.events import EventSummary
from app.api.v1.schemas.search import LessonCard
from app.db.vocab import AzimuthReference, CementReturns, FluidType


class ProximityMode(StrEnum):
    SURFACE = "SURFACE"
    AT_FORMATION = "AT_FORMATION"
    CLOSEST_APPROACH = "CLOSEST_APPROACH"


class WellSummary(ResponseModel):
    id: int
    name: str
    field: str
    status: str
    well_type: str | None = Field(description="Purpose: exploration / development / appraisal")
    fluid_type: FluidType | None = Field(default=None, description="oil | gas | water (B2)")
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


class CementJobOut(Extracted):
    id: int
    toc_md_m: float | None
    toc_tvdss_m: float | None
    returns: CementReturns | None
    slurry_density_sg: float | None
    volume_m3: float | None
    bond_quality: str | None
    remedial: str | None


class CasingOut(Extracted):
    """``od_in``/``hole_size_in``/``weight_ppf`` are nominal industry designations."""

    id: int
    od_in: float | None
    hole_size_in: float | None
    shoe_md_m: float | None
    shoe_tvd_m: float | None
    shoe_tvdss_m: float | None
    planned_shoe_md_m: float | None
    grade: str | None
    weight_ppf: float | None
    cement: list[CementJobOut]


class MudIntervalOut(Extracted):
    id: int
    md_from_m: float
    md_to_m: float
    tvdss_from_m: float | None
    tvdss_to_m: float | None
    hole_size_in: float | None
    mud_type: str | None
    mw_sg: float | None
    ecd_sg: float | None


class DocumentsOverview(ResponseModel):
    """Counts of this well's documents by type and by pipeline stage status."""

    total: int = 0
    by_doc_type: dict[str, int] = Field(
        default_factory=dict, description="Documents per doc_type ('unknown' when unclassified)"
    )
    by_ingest_status: dict[str, int] = Field(default_factory=dict)
    by_extract_status: dict[str, int] = Field(default_factory=dict)
    by_index_status: dict[str, int] = Field(default_factory=dict)


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
    # ── Well 360 enrichment (B2) ──
    casing: list[CasingOut] = Field(default_factory=list, description="Ordered by shoe depth")
    mud: list[MudIntervalOut] = Field(default_factory=list, description="Ordered by md_from_m")
    event_counts: dict[str, int] = Field(
        default_factory=dict, description="Active events per event_type code"
    )
    recent_events: list[EventSummary] = Field(
        default_factory=list, description="Latest active events, newest first (at most 10)"
    )
    documents: DocumentsOverview = Field(default_factory=DocumentsOverview)
    lessons: list[LessonCard] = Field(
        default_factory=list, description="Lesson cards of this well's events (at most 10)"
    )


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


class TrajectoryAtDepth(ResponseModel):
    """Position at ``md_m``, interpolated along the minimum-curvature arc between stations."""

    well_id: int
    wellbore_id: int
    md_m: float
    tvd_m: float
    tvdss_m: float
    north_m: float
    east_m: float
    inc_deg: float
    azi_deg: float
    lat: float
    lon: float
    formation: str | None = Field(description="Formation at this depth, from the tops")
    assumed: bool = Field(description="True when the trajectory is assumed vertical")


class SurveyStationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    md_m: float = Field(ge=0, le=15000)
    inc_deg: float = Field(ge=0, le=180)
    azi_deg: float = Field(ge=0, lt=360)


class SurveyUpload(BaseModel):
    """Survey stations; the server recomputes TVD/TVDSS/N/E/DLS by minimum curvature,
    rebuilds the 3D path and formation entry points, and returns the new trajectory."""

    model_config = ConfigDict(extra="forbid")

    stations: list[SurveyStationIn] = Field(min_length=2, max_length=5000)
    azi_ref: AzimuthReference = "true"
    correction_deg: float | None = Field(
        default=None,
        ge=-180,
        le=180,
        description="Added to every azimuth to reach true north: magnetic declination "
        "(azi_ref=magnetic) or grid convergence (azi_ref=grid). Required unless azi_ref=true.",
    )

    # Validators raise PydanticCustomError, not ValueError: the error handler serialises
    # exc.errors() as JSON and a ValueError in ``ctx`` is not serialisable.
    @model_validator(mode="after")
    def _check(self) -> "SurveyUpload":
        mds = [s.md_m for s in self.stations]
        if any(b <= a for a, b in pairwise(mds)):
            raise PydanticCustomError("value_error", "station md_m must be strictly increasing")
        if self.azi_ref != "true" and self.correction_deg is None:
            raise PydanticCustomError(
                "value_error", "correction_deg is required when azi_ref is not 'true'"
            )
        return self


class OffsetOut(ResponseModel):
    well_id: int
    name: str
    status: str
    well_type: str | None
    fluid_type: FluidType | None = None
    lat: float
    lon: float
    td_md_m: float | None
    synthetic: bool
    distance_m: float = Field(description="Meaning depends on the mode: see distance_label")
    bearing_deg: float | None
    # AT_FORMATION: where the offset well enters the formation
    entry_md_m: float | None = None
    entry_tvdss_m: float | None = None
    # CLOSEST_APPROACH: the pair of measured depths where the two paths are closest
    closest_subject_md_m: float | None = None
    closest_offset_md_m: float | None = None
    closest_tvdss_m: float | None = Field(
        default=None, description="Offset-well TVDSS at the closest-approach point"
    )


class OffsetsOut(ResponseModel):
    well_id: int
    mode: ProximityMode
    radius_km: float
    formation: str | None
    tvdss_from_m: float | None = None
    tvdss_to_m: float | None = None
    distance_label: str = Field(
        default="Surface distance between wellheads",
        description="What distance_m measures in this mode (shown as the column title)",
    )
    subject_entry_md_m: float | None = Field(
        default=None, description="AT_FORMATION: the subject well's formation entry MD"
    )
    subject_entry_tvdss_m: float | None = None
    offsets: list[OffsetOut]
    excluded: list[ExcludedWell] = Field(
        default_factory=list,
        description="Wells in range but left out, with the reason (e.g. 'no Barail top')",
    )


class FormationOut(BaseModel):
    id: int
    basin: str
    name: str
    synonyms: list[str]
    strat_order: int
    lithology: str | None
