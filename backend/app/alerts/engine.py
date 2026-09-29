"""S9 alert decisions for one well: dedupe, fusion, cooldown, budget, evidence rule.

Pure logic over data time (the stream's timestamps, not the wall clock), so a replay at
60x behaves as the same hours would live, and every rule is unit-testable:

- **Evidence rule**: a candidate without evidence is never raised (the DB also refuses it).
- **Dedupe/fusion**: an open (new) alert of the same event type within 30 m TVD absorbs a
  new candidate. From another source it becomes FUSED (the sources agree, the severity is
  the higher one); from the same source it is a duplicate.
- **Cooldown**: for 30 min of data time after an alert is acknowledged or dismissed, the
  same event type within 30 m TVD is not raised again.
- **Budget**: at most 6 non-critical alerts per 12 h of data time. Critical alerts (a kick)
  are exempt and never suppressed by it.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

DEDUPE_TVD_M = 30.0
COOLDOWN = timedelta(minutes=30)
BUDGET = 6
BUDGET_WINDOW = timedelta(hours=12)
SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}
CRITICAL_TYPES = ("KICK",)


@dataclass
class Candidate:
    alert_type: str  # LOOKAHEAD | ANOMALY_ML | PHYSICS | DEJA_VU
    event_type: str
    severity: str
    score: float | None
    score_kind: str  # probability | similarity | indicator | prior
    t_data: datetime
    title: str
    message: str
    md_m: float | None = None
    tvdss_m: float | None = None
    formation: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    drivers: list[dict[str, Any]] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def budget_exempt(self) -> bool:
        return self.severity == "critical"


@dataclass
class Tracked:
    id: int
    event_type: str
    tvdss_m: float | None
    t_data: datetime
    sources: set[str]
    severity: str
    budget_exempt: bool
    status: str = "new"
    closed_at_data: datetime | None = None  # data time of ack / dismiss


@dataclass(frozen=True)
class Decision:
    action: str  # create | fuse | suppress
    reason: str
    target: Tracked | None = None


def _near(a: float | None, b: float | None) -> bool:
    return a is None or b is None or abs(a - b) <= DEDUPE_TVD_M


@dataclass
class AlertEngine:
    alerts: list[Tracked] = field(default_factory=list)
    suppressed: dict[str, int] = field(default_factory=dict)

    def decide(self, c: Candidate) -> Decision:
        if not c.evidence:
            return self._suppress("no evidence")
        same = [
            a for a in self.alerts if a.event_type == c.event_type and _near(a.tvdss_m, c.tvdss_m)
        ]
        for a in same:
            if a.status == "new":
                if c.alert_type in a.sources:
                    return self._suppress("duplicate")
                return Decision("fuse", "another source agrees", a)
        for a in same:
            if a.closed_at_data is not None and c.t_data - a.closed_at_data < COOLDOWN:
                return self._suppress("cooldown")
        if not c.budget_exempt:
            recent = [
                a
                for a in self.alerts
                if not a.budget_exempt and c.t_data - a.t_data < BUDGET_WINDOW
            ]
            if len(recent) >= BUDGET:
                return self._suppress("budget")
        return Decision("create", "new")

    def _suppress(self, reason: str) -> Decision:
        self.suppressed[reason] = self.suppressed.get(reason, 0) + 1
        return Decision("suppress", reason)

    def created(self, alert_id: int, c: Candidate) -> Tracked:
        t = Tracked(
            alert_id,
            c.event_type,
            c.tvdss_m,
            c.t_data,
            {c.alert_type},
            c.severity,
            c.budget_exempt,
        )
        self.alerts.append(t)
        return t

    def fused(self, target: Tracked, c: Candidate) -> None:
        target.sources.add(c.alert_type)
        if SEVERITY_RANK[c.severity] > SEVERITY_RANK[target.severity]:
            target.severity = c.severity

    def closed(self, alert_id: int, status: str, t_data: datetime) -> None:
        """An alert was acknowledged, dismissed or closed at data time `t_data`."""
        for a in self.alerts:
            if a.id == alert_id:
                a.status, a.closed_at_data = status, t_data


def severity_for(event_type: str, strong: bool) -> str:
    if event_type in CRITICAL_TYPES:
        return "critical"
    return "warning" if strong else "info"
