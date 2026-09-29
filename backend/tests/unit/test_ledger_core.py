"""S8 ledger mathematics: outcome rule, posterior, ranking (master plan §Stage 8)."""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.ledger import core


def _uses(code: str, outcomes: str, **kw: object) -> list[core.UseRecord]:
    names = {"s": "success", "p": "partial", "f": "fail", "u": "unknown"}
    return [core.UseRecord(code, names[c], **kw) for c in outcomes]  # type: ignore[arg-type]


def test_recurrence_turns_a_recorded_success_into_partial() -> None:
    assert core.UseRecord("REAM", "success", recurred=True).outcome == "partial"
    assert core.UseRecord("REAM", "success").outcome == "success"
    assert core.UseRecord("REAM", "fail", recurred=True).outcome == "fail"


def test_recurrence_window() -> None:
    ev = core.EventLite(1, 7, "LOSS", 2000.0, 100)
    same = core.EventLite(2, 7, "LOSS", 2040.0, 101)
    assert core.recurred(ev, [ev, same])
    assert not core.recurred(same, [ev, same])  # only a *later* event counts
    assert not core.recurred(ev, [core.EventLite(2, 8, "LOSS", 2000.0, 100)])  # other well
    assert not core.recurred(ev, [core.EventLite(2, 7, "STUCK", 2000.0, 100)])  # other type
    assert not core.recurred(ev, [core.EventLite(2, 7, "LOSS", 2060.0, 100)])  # > 50 m TVD
    assert not core.recurred(ev, [core.EventLite(2, 7, "LOSS", 2000.0, 102)])  # > 24 h
    assert not core.recurred(core.EventLite(1, 7, "LOSS", None, 100), [same])


def test_unknown_outcomes_are_never_counted() -> None:
    (s,) = core.summarise(_uses("LCM_PILL_FINE", "ssfuuu"))
    assert (s.n, s.successes, s.failures, s.unknown) == (3, 2, 1, 3)
    assert s.success_rate == pytest.approx(2 / 3)
    (only_unknown,) = core.summarise(_uses("SQUEEZE", "uu"))
    assert only_unknown.n == 0 and only_unknown.posterior_mean is None
    assert only_unknown.summary == "Squeeze: no recorded outcome (2 unknown)"


def test_posterior_is_beta_1_1() -> None:
    mean, lo, hi = core.posterior(7, 9)
    assert mean == pytest.approx(8 / 11)
    assert lo < 7 / 9 < hi
    # Beta(2, 1) has CDF x², so its quantiles are √q: a closed-form check of the CI.
    mean, lo, hi = core.posterior(1, 1)
    assert (mean, lo, hi) == pytest.approx((2 / 3, math.sqrt(0.05), math.sqrt(0.95)))
    assert core.posterior(0, 0)[1:] == pytest.approx((0.05, 0.95))


def test_ranking_needs_min_n_and_orders_by_posterior() -> None:
    summaries = core.summarise(
        [
            *_uses("LCM_PILL_COARSE", "sssf"),  # 3/4 → 0.667
            *_uses("LCM_PILL_FINE", "ssff"),  # 2/4 → 0.5
            *_uses("REDUCE_MW", "sff"),  # 1/3 → 0.4
            *_uses("CEMENT_PLUG", "ss"),  # n = 2: not ranked however good
            *_uses("REDUCE_FLOW_RATE", "suuu"),  # n = 1
        ]
    )
    ranked, rest = core.rank(summaries)
    assert [s.action_code for s in ranked] == ["LCM_PILL_COARSE", "LCM_PILL_FINE", "REDUCE_MW"]
    assert [s.action_code for s in rest] == ["CEMENT_PLUG", "REDUCE_FLOW_RATE"]
    ranked, rest = core.rank(summaries, min_n=1)
    assert ranked[0].action_code == "CEMENT_PLUG"  # (1 + 2) / (2 + 2): its n = 2 now ranks
    assert not rest


def test_strata_first_choice_and_npt() -> None:
    uses = [
        core.UseRecord("JAR_UP", "success", seq=1, severity="high", npt_hours_after=3.0),
        core.UseRecord("JAR_UP", "fail", seq=2, severity="high", npt_hours_after=5.0),
        core.UseRecord("JAR_UP", "success", seq=1, severity=None, npt_hours_after=None),
    ]
    (s,) = core.summarise(uses)
    assert s.by_severity == {"high": (2, 1), "unrecorded": (1, 1)}
    assert s.first_choice == 2
    assert s.median_npt_hours == 4.0
    assert s.summary.startswith("Jar up: worked 2 of 3 (67%; posterior 60%, 90% CI ")
    assert s.summary.endswith(", median 4 h NPT")


@given(st.integers(0, 60).flatmap(lambda n: st.tuples(st.integers(0, n), st.just(n))))
def test_credible_interval_brackets_the_mean(sn: tuple[int, int]) -> None:
    mean, lo, hi = core.posterior(*sn)
    assert 0 <= lo <= mean <= hi <= 1


@given(st.lists(st.sampled_from(["success", "partial", "fail", "unknown"]), max_size=40))
def test_counts_add_up(outcomes: list[str]) -> None:
    (s,) = core.summarise([core.UseRecord("REAM", o) for o in outcomes]) or [
        core.Summary("REAM", 0, 0, 0, 0, 0, 0, None, None, None, None, None, None)
    ]
    assert s.successes + s.partial + s.failures == s.n
    assert s.n + s.unknown == len(outcomes)
    ranked, rest = core.rank([s], min_n=3)
    assert all(r.n >= 3 for r in ranked) and all(r.n < 3 for r in rest)
