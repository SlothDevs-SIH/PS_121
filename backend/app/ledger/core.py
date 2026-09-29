"""Ledger mathematics (S8), independent of the database so the evaluation can run it on
any record set (including a large generated field).

Outcome rule (master plan §Stage 8):
- ``success``: the event was resolved by this action and the same problem did not come
  back in the same well within ``RECURRENCE_TVD_M`` TVD and ``RECURRENCE_DAYS``;
  a recorded success that recurred counts as ``partial``.
- ``partial`` and ``fail`` count as uses that did not (fully) work.
- ``unknown`` outcomes are never counted either way; they are reported separately.

Rates are Beta(1, 1) posteriors with 90% equal-tailed credible intervals. Only actions
with at least ``min_n`` known outcomes are ranked.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from statistics import median

from scipy.stats import beta

RECURRENCE_TVD_M = 50.0
RECURRENCE_DAYS = 1
MIN_N = 3
PRIOR_A = 1.0
PRIOR_B = 1.0

OUTCOME_RULE = (
    "success = resolved by this action with no recurrence of the same problem in the same "
    f"well within {RECURRENCE_TVD_M:.0f} m TVD / {RECURRENCE_DAYS * 24} h (a recurrence turns "
    "a recorded success into 'partial'); partial and fail count as not working; unknown "
    "outcomes are excluded. Rates: Beta(1,1) posterior mean with a 90% credible interval; "
    f"ranked only when n ≥ {MIN_N}."
)
CAVEAT = (
    "Observational records: an action ranked higher is associated with better recorded "
    "outcomes, not proven to cause them. Harder cases may receive stronger treatments "
    "(confounding by severity): compare within a severity where counts allow."
)

ACTION_LABELS = {
    "LCM_PILL_COARSE": "LCM pill (coarse)",
    "LCM_PILL_FINE": "LCM pill (fine)",
    "LCM_BACKGROUND": "Background LCM",
    "REDUCE_MW": "Reduce mud weight",
    "INCREASE_MW": "Increase mud weight",
    "REDUCE_FLOW_RATE": "Reduce flow rate",
    "INCREASE_FLOW": "Increase flow rate",
    "CEMENT_PLUG": "Cement plug",
    "SQUEEZE": "Squeeze",
    "REMEDIAL_SQUEEZE": "Remedial squeeze",
    "TOP_JOB": "Top job",
    "SPOT_PIPE_RELEASE_PILL": "Pipe-release pill",
    "JAR_UP": "Jar up",
    "JAR_DOWN": "Jar down",
    "WORK_PIPE": "Work pipe",
    "BACKOFF_AND_FISH": "Back off and fish",
    "FISHING": "Fishing",
    "SIDETRACK": "Sidetrack",
    "WAIT_AND_WEIGHT": "Wait and weight",
    "DRILLERS_METHOD": "Driller's method",
    "BULLHEAD": "Bullhead",
    "REAM": "Ream / back-ream",
    "WIPER_TRIP": "Wiper trip",
    "ADD_LUBRICANT": "Add lubricant",
    "REDUCE_RPM": "Reduce RPM",
    "ADD_DETERGENT": "Add detergent",
    "CHANGE_BHA": "Change BHA",
    "CIRCULATE": "Circulate",
    "OTHER": "Other (unclassified)",
}


def label(code: str) -> str:
    return ACTION_LABELS.get(code, code.replace("_", " ").capitalize())


@dataclass
class UseRecord:
    """One use of an action against one event, with its recorded outcome."""

    action_code: str
    recorded_outcome: str
    seq: int = 1
    recurred: bool = False
    severity: str | None = None
    npt_hours_after: float | None = None
    volume_lost_m3: float | None = None
    key: int = -1  # the caller's index for this use (cases, evidence)

    @property
    def outcome(self) -> str:
        if self.recorded_outcome == "success" and self.recurred:
            return "partial"
        return self.recorded_outcome


@dataclass
class Summary:
    action_code: str
    n: int
    successes: int
    partial: int
    failures: int
    unknown: int
    first_choice: int
    success_rate: float | None
    posterior_mean: float | None
    ci90_low: float | None
    ci90_high: float | None
    median_npt_hours: float | None
    median_volume_lost_m3: float | None
    by_severity: dict[str, tuple[int, int]] = field(default_factory=dict)
    uses: list[UseRecord] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.n == 0:
            return f"{label(self.action_code)}: no recorded outcome ({self.unknown} unknown)"
        text = f"{label(self.action_code)}: worked {self.successes} of {self.n}"
        if self.posterior_mean is not None and self.n >= MIN_N:
            text += (
                f" ({self.success_rate:.0%}; posterior {self.posterior_mean:.0%}, "
                f"90% CI {self.ci90_low:.0%}–{self.ci90_high:.0%})"
            )
        if self.median_npt_hours is not None:
            text += f", median {self.median_npt_hours:g} h NPT"
        return text


def posterior(successes: int, n: int) -> tuple[float, float, float]:
    a, b = PRIOR_A + successes, PRIOR_B + n - successes
    lo = float(beta.ppf(0.05, a, b))
    hi = float(beta.ppf(0.95, a, b))
    return a / (a + b), lo, hi


def summarise(uses: Iterable[UseRecord]) -> list[Summary]:
    by_code: dict[str, list[UseRecord]] = {}
    for u in uses:
        by_code.setdefault(u.action_code, []).append(u)
    out = []
    for code, us in by_code.items():
        known = [u for u in us if u.outcome != "unknown"]
        s = sum(u.outcome == "success" for u in known)
        p = sum(u.outcome == "partial" for u in known)
        f = sum(u.outcome == "fail" for u in known)
        n = len(known)
        mean = lo = hi = rate = None
        if n:
            mean, lo, hi = posterior(s, n)
            rate = s / n
        npts = [u.npt_hours_after for u in known if u.npt_hours_after is not None]
        vols = [u.volume_lost_m3 for u in known if u.volume_lost_m3 is not None]
        strata: dict[str, tuple[int, int]] = {}
        for u in known:
            key = u.severity or "unrecorded"
            nn, ss = strata.get(key, (0, 0))
            strata[key] = (nn + 1, ss + (u.outcome == "success"))
        out.append(
            Summary(
                action_code=code,
                n=n,
                successes=s,
                partial=p,
                failures=f,
                unknown=len(us) - n,
                first_choice=sum(u.seq == 1 for u in us),
                success_rate=rate,
                posterior_mean=mean,
                ci90_low=lo,
                ci90_high=hi,
                median_npt_hours=round(median(npts), 2) if npts else None,
                median_volume_lost_m3=round(median(vols), 2) if vols else None,
                by_severity=strata,
                uses=us,
            )
        )
    return out


def rank(summaries: list[Summary], min_n: int = MIN_N) -> tuple[list[Summary], list[Summary]]:
    """(ranked, insufficient): ranked by posterior mean, then n; insufficient by n."""
    ranked = sorted(
        (s for s in summaries if s.n >= min_n),
        key=lambda s: (-(s.posterior_mean or 0), -s.n, s.action_code),
    )
    rest = sorted((s for s in summaries if s.n < min_n), key=lambda s: (-s.n, s.action_code))
    return ranked, rest


@dataclass
class EventLite:
    """What recurrence detection needs about an event."""

    id: int
    well_id: int
    event_type: str
    tvdss_m: float | None
    day: int | None  # date ordinal


def recurred(ev: EventLite, others: list[EventLite]) -> bool:
    """A later event of the same type in the same well, close in TVD and time."""
    if ev.tvdss_m is None or ev.day is None:
        return False
    for o in others:
        if (
            o.id != ev.id
            and o.well_id == ev.well_id
            and o.event_type == ev.event_type
            and o.tvdss_m is not None
            and o.day is not None
            and 0 <= o.day - ev.day <= RECURRENCE_DAYS
            and abs(o.tvdss_m - ev.tvdss_m) <= RECURRENCE_TVD_M
            and (o.day, o.id) > (ev.day, ev.id)
        ):
            return True
    return False
