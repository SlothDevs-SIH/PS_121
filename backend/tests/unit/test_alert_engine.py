"""S9 alert engine rules: evidence, dedupe/fusion, cooldown, budget, critical exemption."""

from datetime import datetime, timedelta

from app.alerts.engine import BUDGET, AlertEngine, Candidate, severity_for

T0 = datetime(2026, 9, 28, 18, 0)
EV = [{"kind": "stream", "wellbore_id": 1}]


def cand(
    source: str = "ANOMALY_ML",
    et: str = "LOSS",
    minutes: float = 0,
    tvdss: float | None = 2000.0,
    severity: str = "warning",
    evidence: list[dict[str, object]] | None = None,
) -> Candidate:
    return Candidate(
        source, et, severity, 0.7, "probability", T0 + timedelta(minutes=minutes), "t", "m",
        tvdss_m=tvdss, evidence=EV if evidence is None else evidence,
    )  # fmt: skip


def test_no_evidence_no_alert() -> None:
    eng = AlertEngine()
    assert eng.decide(cand(evidence=[])).reason == "no evidence"
    assert eng.suppressed == {"no evidence": 1}


def test_same_source_is_a_duplicate_and_another_source_fuses() -> None:
    eng = AlertEngine()
    first = cand()
    assert eng.decide(first).action == "create"
    tracked = eng.created(1, first)
    assert eng.decide(cand(minutes=5, tvdss=2010)).reason == "duplicate"
    d = eng.decide(cand("PHYSICS", minutes=6, tvdss=2020, severity="critical"))
    assert d.action == "fuse" and d.target is tracked
    eng.fused(tracked, cand("PHYSICS", severity="critical"))
    assert tracked.sources == {"ANOMALY_ML", "PHYSICS"} and tracked.severity == "critical"
    # Another event type, or the same type 30+ m TVD away, is a separate alert.
    assert eng.decide(cand(et="KICK")).action == "create"
    assert eng.decide(cand(tvdss=2031)).action == "create"


def test_cooldown_after_ack_then_realert() -> None:
    eng = AlertEngine()
    eng.created(1, cand())
    eng.closed(1, "ack", T0 + timedelta(minutes=10))
    assert eng.decide(cand(minutes=39)).reason == "cooldown"
    assert eng.decide(cand(minutes=41)).action == "create"


def test_budget_caps_non_critical_but_never_a_kick() -> None:
    eng = AlertEngine()
    for i in range(BUDGET):
        c = cand(et=f"T{i}", minutes=i)
        assert eng.decide(c).action == "create"
        eng.created(i, c)
    assert eng.decide(cand(et="OTHER", minutes=30)).reason == "budget"
    kick = cand("PHYSICS", "KICK", minutes=31, severity=severity_for("KICK", strong=False))
    assert kick.severity == "critical" and eng.decide(kick).action == "create"
    # The window is 12 h of data time.
    assert eng.decide(cand(et="OTHER", minutes=12 * 60 + 10)).action == "create"


def test_severity_rules() -> None:
    assert severity_for("KICK", strong=False) == "critical"
    assert severity_for("LOSS", strong=True) == "warning"
    assert severity_for("LOSS", strong=False) == "info"
