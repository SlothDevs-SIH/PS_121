"""Drilling events, mitigations, DDR NPT lines and lessons-learned card text (S2, B2).

Depths are canonical metres (``md_m``/``tvd_m``/``tvdss_m``; TVDSS positive downwards below
mean sea level); mud weights are specific gravity (``_sg``); volumes m3; forces kN;
pressures kPa; torque kN.m. The UI converts for display (app/core/units.py holds the factors).
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.api.v1.schemas.common import EvidenceRef, EvidenceRefIn, Extracted, ResponseModel
from app.db.vocab import (
    ActionCode,
    EventSource,
    EventStatus,
    EventType,
    MitigationOutcome,
    Severity,
)


class _EventParamsFields(BaseModel):
    """Type-specific numbers in canonical units (stored in ``event.params``). Only the keys
    that apply to an event type are set; everything else is null."""

    loss_rate_m3_h: float | None = Field(default=None, ge=0)  # LOSS
    total_loss_m3: float | None = Field(default=None, ge=0)  # LOSS
    time_to_cure_h: float | None = Field(default=None, ge=0)  # LOSS
    ecd_sg: float | None = Field(default=None, gt=0)  # LOSS / KICK
    pit_gain_m3: float | None = Field(default=None, ge=0)  # KICK
    sidpp_kpa: float | None = Field(default=None, ge=0)  # KICK
    sicp_kpa: float | None = Field(default=None, ge=0)  # KICK
    kill_mw_sg: float | None = Field(default=None, gt=0)  # KICK
    overpull_kn: float | None = Field(default=None, ge=0)  # STUCK / TIGHT
    jarring_h: float | None = Field(default=None, ge=0)  # STUCK
    torque_knm: float | None = Field(default=None, ge=0)  # TORQUE
    gas_pct: float | None = Field(default=None, ge=0, le=100)  # GAS / OVERP
    h2s_ppm: float | None = Field(default=None, ge=0)  # GAS


class EventParams(_EventParamsFields):
    """Event parameters as returned (every key present, null when not recorded)."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class EventParamsIn(_EventParamsFields):
    """Event parameters as supplied by a client; unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")


class LessonCardContent(ResponseModel):
    """Problem -> likely cause -> action taken -> outcome -> lesson (master plan Stage 5),
    stored in ``event.lesson_card``. Advisory wording; every line is grounded in the event's
    evidence. ``generated_by`` names the template or model that wrote it."""

    problem: str
    likely_cause: str | None = None
    action_taken: str | None = None
    outcome: str | None = None
    lesson: str | None = None
    generated_by: str


class MitigationOut(Extracted):
    id: int
    seq: int = Field(description="Order in which the action was tried (1 = first)")
    action_code: ActionCode
    action_text: str | None
    t_start: datetime | None
    outcome: MitigationOutcome
    npt_hours_after: float | None
    volume_lost_m3: float | None
    recurrence: bool | None


class EventSummary(Extracted):
    id: int
    well_id: int
    well_name: str
    wellbore_id: int | None
    synthetic: bool = Field(description="True when the well belongs to a SYNTHETIC field")
    event_type: EventType
    subtype: str | None
    severity: Severity | None
    event_date: date | None
    t_start: datetime | None
    t_end: datetime | None
    md_m: float | None
    tvd_m: float | None
    tvdss_m: float | None
    formation_id: int | None
    formation: str | None = Field(description="Formation name at the event depth")
    hole_size_in: float | None
    mw_sg: float | None
    npt_hours: float | None
    resolved: bool | None
    source: EventSource
    status: EventStatus


class EventDetail(EventSummary):
    params: EventParams
    cause_text: str | None
    description: str | None
    lesson_card: LessonCardContent | None
    mitigations: list[MitigationOut]
    verified_by: str | None
    verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EventPage(ResponseModel):
    """Cursor page: pass ``next_cursor`` back as ``cursor``; null means the last page."""

    items: list[EventSummary]
    next_cursor: str | None


class MitigationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_code: ActionCode
    action_text: str | None = Field(default=None, max_length=2000)
    t_start: datetime | None = None
    outcome: MitigationOutcome = "unknown"
    npt_hours_after: float | None = Field(default=None, ge=0)
    volume_lost_m3: float | None = Field(default=None, ge=0)
    recurrence: bool | None = None
    evidence: list[EvidenceRefIn] = Field(default_factory=list, max_length=20)


class EventCreate(BaseModel):
    """Manual event entry. Stored with ``source='manual'`` and ``verified=false`` until a
    reviewer verifies it; without evidence the UI shows it as uncited."""

    model_config = ConfigDict(extra="forbid")

    well_id: int
    wellbore_id: int | None = None
    event_type: EventType
    subtype: str | None = Field(default=None, max_length=40)
    severity: Severity | None = None
    event_date: date | None = None
    t_start: datetime | None = None
    t_end: datetime | None = None
    md_m: float | None = Field(default=None, ge=0, le=15000)
    formation_id: int | None = None
    hole_size_in: float | None = Field(default=None, gt=0, le=40)
    mw_sg: float | None = Field(default=None, ge=0.8, le=2.6)
    params: EventParamsIn = Field(default_factory=EventParamsIn)
    cause_text: str | None = Field(default=None, max_length=4000)
    description: str | None = Field(default=None, max_length=8000)
    npt_hours: float | None = Field(default=None, ge=0)
    resolved: bool | None = None
    mitigations: list[MitigationCreate] = Field(default_factory=list, max_length=20)
    evidence: list[EvidenceRefIn] = Field(default_factory=list, max_length=50)

    # PydanticCustomError (not ValueError) keeps exc.errors() JSON-serialisable.
    @model_validator(mode="after")
    def _time_order(self) -> "EventCreate":
        if self.t_start and self.t_end and self.t_end < self.t_start:
            raise PydanticCustomError("value_error", "t_end must not be before t_start")
        return self


class EventVerify(BaseModel):
    """Verify (or un-verify) an event, or reject it as not a real event."""

    model_config = ConfigDict(extra="forbid")

    verified: bool = True
    status: EventStatus | None = Field(
        default=None, description="Set 'rejected' to hide a false extraction; null = unchanged"
    )
    note: str | None = Field(default=None, max_length=2000)


class DdrOperationOut(ResponseModel):
    """One DDR time-log line (NPT lines appear on the well timeline)."""

    id: int
    document_id: int
    page_no: int | None
    report_date: date | None
    t_from: datetime | None
    t_to: datetime | None
    hours: float | None
    md_m: float | None
    activity_code: str | None
    description: str
    is_npt: bool
    npt_category: str | None
    event_id: int | None
    evidence: list[EvidenceRef]


class EventTimeline(ResponseModel):
    """Chronological events of one well (ordered by event_date / t_start, then md_m;
    undated events last), with the DDR NPT lines and per-type counts."""

    well_id: int
    well_name: str
    synthetic: bool
    spud_date: date | None
    completion_date: date | None
    td_md_m: float | None
    events: list[EventSummary]
    npt_operations: list[DdrOperationOut]
    counts_by_type: dict[str, int] = Field(description="Active events per event_type code")
    total_npt_hours: float | None = Field(description="Sum over events; null if none recorded")
