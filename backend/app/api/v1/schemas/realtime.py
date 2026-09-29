"""Real-time API: replay sessions, the live window of a well, alerts (S12, S7b-d, S9)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.common import EvidenceRef, ResponseModel
from app.db.vocab import AlertSeverity, AlertStatus, AlertType, AlertVerdict, ReplayStatus

ReplayAction = Literal["start", "pause", "resume", "stop", "speed"]


class ReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    well_id: int
    action: ReplayAction = "start"
    speed: float = Field(60.0, ge=1, le=2000, description="Data seconds per wall second")


class ReplaySessionOut(ResponseModel):
    id: int
    well_id: int
    well_name: str
    wellbore_id: int
    source_uri: str
    speed: float
    status: ReplayStatus
    position: int = Field(description="Rows published so far")
    total_rows: int | None
    data_start: datetime | None
    data_now: datetime | None = Field(description="Timestamp of the last published row")
    error: str | None
    synthetic: bool
    created_at: datetime
    updated_at: datetime


class StreamStatus(ResponseModel):
    service_alive: bool = Field(description="The stream service sent a heartbeat in the last 15 s")
    heartbeat: dict[str, Any] | None
    sessions: list[ReplaySessionOut]


class RealtimeWindow(ResponseModel):
    """The last minutes of a well's stream, downsampled, for the live view's first paint
    (then /ws/wells/{well_id}/live pushes frames)."""

    well_id: int
    well_name: str
    wellbore_id: int | None
    synthetic: bool
    session: ReplaySessionOut | None
    channels: list[str]
    units: dict[str, str]
    ts: list[datetime]
    values: dict[str, list[float | None]]
    rig_state: list[str | None]
    scores_ts: list[datetime]
    scores: dict[str, list[float | None]] = Field(
        description="Classifier probability per event type, one value per scored minute"
    )
    thresholds: dict[str, float] = Field(description="Alert threshold per event type")
    latest: dict[str, Any] | None = Field(description="The most recent scoring frame")
    stale: bool = Field(description="No sample for over 60 s of wall time while a replay runs")


class AlertEvidence(ResponseModel):
    """One piece of evidence: a window of the well's own stream, or a past event (an offset
    well's in this formation, or the one a Déjà Vu match preceded) with its report pages."""

    kind: Literal["stream", "offset_event", "matched_event"]
    wellbore_id: int | None = None
    t_from: datetime | None = None
    t_to: datetime | None = None
    channels: list[str] = Field(default_factory=list)
    event_id: int | None = None
    well_id: int | None = None
    well_name: str | None = None
    event_type: str | None = None
    md_m: float | None = None
    formation: str | None = None
    refs: list[EvidenceRef] = Field(default_factory=list)


class AlertDriver(ResponseModel):
    feature: str
    label: str
    value: float | None
    typical: float
    contribution: float = Field(description="Drop in probability when reset to typical")


class AlertRecommendation(ResponseModel):
    action_code: str
    action_label: str
    summary: str
    n: int
    posterior_mean: float | None
    ci90_low: float | None
    ci90_high: float | None
    insufficient: bool = Field(description="Fewer uses than the ledger's minimum: not ranked")


class AlertOut(ResponseModel):
    id: int
    well_id: int
    well_name: str
    synthetic: bool
    wellbore_id: int | None
    session_id: int | None
    alert_type: AlertType
    event_type: str
    severity: AlertSeverity
    status: AlertStatus
    title: str
    message: str
    score: float | None
    score_kind: str = Field(
        description="probability (classifier) | similarity (Déjà Vu, not a probability) | "
        "indicator (physics rule value) | prior (offset prior probability)"
    )
    md_m: float | None
    tvdss_m: float | None
    formation: str | None
    t_data: datetime = Field(description="Data time the alert was raised at")
    created_at: datetime
    sources: list[str]
    evidence: list[AlertEvidence]
    drivers: list[AlertDriver]
    recommendations: list[AlertRecommendation]
    detail: dict[str, Any]
    budget_exempt: bool
    acked_by: str | None
    acked_at: datetime | None
    dismiss_reason: str | None
    feedback: list["AlertFeedbackOut"]


class AlertPage(ResponseModel):
    items: list[AlertOut]
    counts: dict[str, int] = Field(description="Alerts by status in the filtered scope")


class AlertDismiss(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)


class AlertFeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: AlertVerdict
    comment: str | None = Field(None, max_length=1000)


class AlertFeedbackOut(ResponseModel):
    id: int
    alert_id: int
    verdict: AlertVerdict
    comment: str | None
    user_id: str
    created_at: datetime


AlertOut.model_rebuild()


class DejaVuOverlay(ResponseModel):
    """The live 30 minutes behind a Déjà Vu alert beside the past incident's run-up it
    matched, each channel as the matcher saw it (operating state only, gaps held)."""

    alert_id: int
    signature_id: int
    event_type: str
    matched_well_id: int | None
    matched_well_name: str | None
    matched_event_id: int | None
    formation: str | None = Field(description="Formation of the past event")
    similarity: float = Field(description="Similarity at alert time: 0-1, not a probability")
    minutes_before_event: float = Field(
        description="How long before the past event the matched segment ends"
    )
    dt_s: int
    channels: list[str]
    live: dict[str, list[float]] | None = Field(
        description="The 30 min ending at the alert's data time; null if no longer stored"
    )
    matched: dict[str, list[float]] = Field(description="The matched 30 min of the signature")
    signature: dict[str, list[float]] = Field(description="The whole 90-min signature")
    note: str
