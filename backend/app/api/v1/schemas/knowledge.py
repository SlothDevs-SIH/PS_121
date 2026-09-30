"""Mitigation Effectiveness Ledger (S8, USP 2) and offset prior risk (S7a), B3.

Probabilities here are **posterior estimates with credible intervals** from recorded
outcomes and offset wells: observational, "associated with", never causal. Counts are
always returned next to rates so a reader can judge how much evidence there is.
"""

from pydantic import Field

from app.api.v1.schemas.common import EvidenceRef, ResponseModel
from app.db.vocab import EventType, MitigationOutcome


class LedgerCase(ResponseModel):
    """One recorded use of an action: click-through to the event and its report pages."""

    event_id: int
    mitigation_id: int
    well_id: int
    well_name: str
    synthetic: bool
    event_date: str | None
    formation: str | None
    severity: str | None
    seq: int = Field(description="Order the action was tried in (1 = first)")
    outcome: MitigationOutcome = Field(description="Outcome as used by the ledger")
    recorded_outcome: MitigationOutcome = Field(description="Outcome as extracted")
    recurred: bool = Field(description="Same problem came back within the recurrence window")
    npt_hours_after: float | None
    verified: bool
    evidence: list[EvidenceRef]


class SeverityStratum(ResponseModel):
    severity: str
    n: int
    successes: int


class LedgerEntry(ResponseModel):
    action_code: str
    action_label: str
    n: int = Field(description="Uses with a known outcome (success + partial + fail)")
    successes: int
    partial: int
    failures: int
    unknown: int = Field(description="Uses whose outcome was not recorded: excluded from n")
    first_choice: int = Field(description="Uses where it was the first action tried")
    success_rate: float | None = Field(description="successes / n (raw)")
    posterior_mean: float | None = Field(description="Beta(1,1) prior → posterior mean")
    ci90_low: float | None
    ci90_high: float | None
    median_npt_hours: float | None
    median_volume_lost_m3: float | None
    by_severity: list[SeverityStratum]
    summary: str = Field(description="One-line reading, e.g. 'worked 7 of 9 (78%, 90% CI …)'")
    cases: list[LedgerCase]


class LedgerScope(ResponseModel):
    wells: int
    events: int
    mitigations: int
    unknown_outcomes: int


class LedgerResponse(ResponseModel):
    event_type: EventType
    formation: str | None
    basin: str | None
    well_id: int | None
    radius_km: float | None
    min_n: int = Field(description="Entries with fewer known outcomes are not ranked")
    outcome_rule: str
    caveat: str
    scope: LedgerScope
    ranked: list[LedgerEntry] = Field(description="n ≥ min_n, best posterior mean first")
    insufficient: list[LedgerEntry] = Field(description="n < min_n: listed with their cases")
    synthetic: bool = Field(description="True when any contributing well is synthetic")


class RiskOffset(ResponseModel):
    well_id: int
    name: str
    synthetic: bool
    distance_m: float
    distance_kind: str = Field(description="'at_formation' (3D entry points) or 'surface'")
    similarity: float = Field(
        description="0.5–1.0: × 0.75 other hole size, × 0.8 other mud system, × 0.9 other well type"
    )
    weight: float = Field(description="exp(−d²/2σ²) × similarity × recency")
    events: dict[str, list[int]] = Field(description="event_type → event ids in this interval")


class EventRisk(ResponseModel):
    event_type: EventType
    probability: float = Field(description="Weighted Beta-Binomial posterior mean")
    ci90_low: float
    ci90_high: float
    n_eff: float = Field(description="(Σw)² / Σw²: how many offsets' worth of evidence")
    offsets_with_event: int
    offsets_total: int
    base_rate: float = Field(description="Basin-wide prior rate for this event type")
    label: str


class BinRisk(ResponseModel):
    event_type: str
    probability: float
    ci90_low: float
    ci90_high: float
    offsets_with_event: int


class RiskBin(ResponseModel):
    """A depth slice of a formation (Part 7, V-B20). Offsets' events are placed by their
    relative position inside their own formation, so a thicker or thinner formation at an
    offset still maps onto the same slice."""

    top_md_m: float
    base_md_m: float
    top_tvdss_m: float
    base_tvdss_m: float
    rel_from: float = Field(description="0 = formation top, 1 = its base")
    rel_to: float
    risks: list[BinRisk] = Field(description="Highest probability first")


class RiskInterval(ResponseModel):
    formation: str
    strat_order: int
    top_md_m: float
    base_md_m: float | None
    top_tvdss_m: float
    base_tvdss_m: float | None
    prognosed: bool = Field(
        False,
        description="Below a drilling well's current TD: the top is the offsets' "
        "inverse-distance-weighted estimate, not a pick",
    )
    prognosis_spread_m: float | None = Field(
        None, description="Weighted spread of the offsets' tops around the prognosed top"
    )
    offsets: list[RiskOffset]
    risks: list[EventRisk] = Field(description="Highest probability first")
    bins: list[RiskBin] = Field(
        default_factory=list,
        description="Depth slices when bin_m is requested (only for intervals with a base)",
    )


class RiskProfile(ResponseModel):
    well_id: int
    name: str
    status: str
    synthetic: bool
    td_md_m: float | None = Field(description="Deepest survey station (MD)")
    td_tvdss_m: float | None = Field(description="Deepest survey station (TVDSS)")
    mode: str = Field(description="Distance used for weights: AT_FORMATION or SURFACE")
    radius_km: float
    sigma_km: float
    prior_strength: float = Field(description="α + β of the basin prior (pseudo-offsets)")
    method: str
    intervals: list[RiskInterval]


class CementingCheck(ResponseModel):
    well_id: int
    formation: str | None
    shoe_md_m: float
    slurry_density_sg: float
    level: str = Field(description="low | medium | high")
    flags: list[str]
    offsets_considered: int
    offset_loss_mw_sg: list[float] = Field(description="Mud weights at offset losses here")
    evidence_event_ids: list[int]
