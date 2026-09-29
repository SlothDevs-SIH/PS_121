"""Correlation panel and formation statistics (S6, B2).

Aligned coordinates (``top``, ``base``, ``aligned``, ``td_aligned``) are positions on the
panel's ``depth_axis``, increasing downwards:
- ``TVDSS``: metres TVDSS;
- ``FLATTEN_ON_TOP``: metres TVDSS relative to the chosen top (0 = the top, + below it);
- ``FORMATION_RELATIVE``: formation index + fractional position inside it (k + 0..1 for
  the k-th formation in stratigraphic order), piecewise-linear between tops.
Wells missing the tops an alignment needs fall back to TVDSS and say why; a missing top is
never interpolated.
"""

from enum import StrEnum

from pydantic import Field

from app.api.v1.schemas.common import EvidenceRef, Extracted, ResponseModel
from app.db.vocab import CementReturns, EventType, FluidType, Severity


class Alignment(StrEnum):
    TVDSS = "TVDSS"
    FLATTEN_ON_TOP = "FLATTEN_ON_TOP"
    FORMATION_RELATIVE = "FORMATION_RELATIVE"


class DepthAxis(ResponseModel):
    label: str = Field(description="Axis title, e.g. 'TVDSS (m)' or 'Relative to Barail top (m)'")
    unit: str = Field(description="'m' or 'formation' (FORMATION_RELATIVE)")
    min: float
    max: float


class FormationTrack(ResponseModel):
    name: str
    strat_order: int
    lithology: str | None
    top: float
    base: float | None = Field(description="Next formation's top or TD; null if unknown")
    top_tvdss_m: float
    base_tvdss_m: float | None


class CasingShoeTrack(Extracted):
    casing_id: int
    od_in: float | None
    hole_size_in: float | None
    shoe_md_m: float | None
    shoe_tvdss_m: float | None
    aligned: float | None


class MudTrack(Extracted):
    mud_interval_id: int
    md_from_m: float
    md_to_m: float
    tvdss_from_m: float | None
    tvdss_to_m: float | None
    top: float | None
    base: float | None
    mud_type: str | None
    mw_sg: float | None
    ecd_sg: float | None


class CementTopTrack(Extracted):
    cement_job_id: int
    casing_id: int
    toc_md_m: float | None
    toc_tvdss_m: float | None
    aligned: float | None
    returns: CementReturns | None


class EventMarker(ResponseModel):
    event_id: int
    event_type: EventType
    severity: Severity | None
    md_m: float | None
    tvdss_m: float | None
    aligned: float | None = Field(description="Null when the event has no usable depth")
    relative_position: float | None = Field(
        description="0 = formation top, 1 = base (FORMATION_RELATIVE only)"
    )
    npt_hours: float | None
    confidence: float = Field(ge=0, le=1)
    verified: bool
    evidence: list[EvidenceRef]


class CorrelationTracks(ResponseModel):
    formations: list[FormationTrack]
    casing_shoes: list[CasingShoeTrack]
    mud: list[MudTrack]
    cement_tops: list[CementTopTrack]
    events: list[EventMarker]


class CorrelationWell(ResponseModel):
    well_id: int
    name: str
    fluid_type: FluidType | None
    status: str
    synthetic: bool
    fallback_to_tvdss: bool = Field(description="True when this well could not be aligned")
    reason: str | None = Field(description="Why it fell back (e.g. 'no Barail top')")
    td_aligned: float | None
    tracks: CorrelationTracks


class CorrelationPanel(ResponseModel):
    align: Alignment
    top: str | None = Field(description="Flattening formation (FLATTEN_ON_TOP)")
    depth_axis: DepthAxis
    wells: list[CorrelationWell]


class FormationStatsRow(ResponseModel):
    formation: str
    strat_order: int
    wells_penetrating: int
    events_by_type: dict[str, int] = Field(description="Active events per event_type code")
    wells_with_event_by_type: dict[str, int] = Field(
        description="Wells with >= 1 event of the type (the '3 of 6 offsets' numerator)"
    )
    median_mw_sg: float | None
    median_npt_hours: float | None


class FormationStats(ResponseModel):
    wells: list[int] = Field(description="Wells the statistics were computed over")
    rows: list[FormationStatsRow]
