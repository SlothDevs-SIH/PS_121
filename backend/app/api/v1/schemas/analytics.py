"""Analytics (B5; the screen is F5): NPT breakdowns, recurring problems, alert quality."""

from typing import Literal

from pydantic import Field

from app.api.v1.schemas.common import ResponseModel

GroupBy = Literal["event_type", "formation", "year", "well", "field"]


class NptRow(ResponseModel):
    key: str = Field(description="The group's value (event type code, formation, year…)")
    events: int
    wells: int
    npt_hours: float
    share_of_npt: float = Field(description="0-1 share of the filtered total NPT")
    median_npt_hours: float | None


class NptBreakdown(ResponseModel):
    group_by: GroupBy
    rows: list[NptRow] = Field(description="Largest NPT first")
    total_events: int
    total_npt_hours: float
    events_without_npt: int = Field(description="Events whose NPT was not recorded (not zero)")
    synthetic: bool


class RecurringRow(ResponseModel):
    event_type: str
    formation: str
    wells: int
    events: int
    npt_hours: float
    first_year: int | None
    last_year: int | None
    event_ids: list[int] = Field(description="Up to 10, for click-through")


class RepeatInWell(ResponseModel):
    well_id: int
    well_name: str
    event_type: str
    events: int
    npt_hours: float


class RecurringProblems(ResponseModel):
    min_wells: int
    across_wells: list[RecurringRow] = Field(
        description="Same problem in the same formation in at least min_wells wells"
    )
    within_wells: list[RepeatInWell] = Field(description="Same problem 2+ times in one well")
    synthetic: bool


class Proportion(ResponseModel):
    """k of n with the Beta(1,1) posterior mean and 90% credible interval (as the ledger)."""

    k: int
    n: int
    mean: float | None
    ci90_low: float | None
    ci90_high: float | None


class AlertQuality(ResponseModel):
    alerts: int
    by_type: dict[str, int]
    by_source: dict[str, int] = Field(description="Counts each source of fused alerts once")
    by_severity: dict[str, int]
    by_status: dict[str, int]
    feedback: dict[str, int] = Field(description="useful / not_useful / false_alarm")
    precision: Proportion = Field(
        description="Alerts marked useful among alerts with feedback (latest verdict each)"
    )
    acknowledged: Proportion
    median_minutes_to_ack: float | None = Field(description="Wall time from raised to acked")
    data_hours: float = Field(description="Hours of stream data scored (replays included)")
    alerts_per_12h: float | None
    note: str
