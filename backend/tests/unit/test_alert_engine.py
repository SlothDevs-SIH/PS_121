"""S9 alert engine rules: evidence, dedupe/fusion, cooldown, budget, critical exemption."""

from datetime import datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from app.alerts.engine import BUDGET, BUDGET_WINDOW, AlertEngine, Candidate, severity_for

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


SOURCES = ("ANOMALY_ML", "PHYSICS", "DEJA_VU", "LOOKAHEAD")
TYPES = ("LOSS", "KICK", "STUCK", "BALLING")


@settings(max_examples=200, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.sampled_from(SOURCES),
            st.sampled_from(TYPES),
            st.floats(0, 24 * 60),
            st.floats(1500, 2500),
            st.booleans(),
            st.booleans(),
        ),
        max_size=60,
    )
)
def test_property_no_alert_without_evidence_and_kicks_never_budgeted(
    stream: list[tuple[str, str, float, float, bool, bool]],
) -> None:
    eng = AlertEngine()
    for i, (src, et, minutes, tvdss, has_ev, ack) in enumerate(sorted(stream, key=lambda s: s[2])):
        c = cand(src, et, minutes, tvdss, severity_for(et, strong=True), EV if has_ev else [])
        d = eng.decide(c)
        if not has_ev:
            assert d.action == "suppress" and d.reason == "no evidence"
        if et == "KICK" and has_ev:
            assert d.reason != "budget"
        if d.action == "create":
            t = eng.created(i, c)
            if ack:
                eng.closed(t.id, "ack", c.t_data)
        elif d.action == "fuse":
            assert d.target is not None and d.target.event_type == et
            eng.fused(d.target, c)
    created = [a for a in eng.alerts if not a.budget_exempt]
    for a in created:  # never more than the budget inside any 12-h window
        window = [b for b in created if timedelta(0) <= a.t_data - b.t_data < BUDGET_WINDOW]
        assert len(window) <= BUDGET
