"""S7a offset prior mathematics: weighted Beta-Binomial with a basin prior."""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.risk import core


def test_no_offsets_returns_the_prior() -> None:
    a, b = core.prior_params(0.1)
    post = core.weighted_beta_binomial([], [], a, b)
    assert post.probability == pytest.approx(0.1)
    assert post.n_eff == 0
    assert post.ci90_low < 0.1 < post.ci90_high


def test_equal_weights_give_the_closed_form() -> None:
    a, b = core.prior_params(0.2)  # alpha = 0.4, beta = 1.6
    post = core.weighted_beta_binomial([1.0] * 10, [True] * 3 + [False] * 7, a, b)
    assert post.probability == pytest.approx((3 + 0.4) / (10 + 2))
    assert post.n_eff == pytest.approx(10)


def test_interval_narrows_as_offsets_accumulate() -> None:
    a, b = core.prior_params(0.3)
    widths = []
    for n in (4, 16, 64):
        post = core.weighted_beta_binomial([1.0] * n, [i % 4 == 0 for i in range(n)], a, b)
        widths.append(post.ci90_high - post.ci90_low)
    assert widths[0] > widths[1] > widths[2]


def test_n_eff_counts_effective_offsets() -> None:
    a, b = core.prior_params(0.1)
    assert core.weighted_beta_binomial([1.0, 0.001, 0.001], [True] * 3, a, b).n_eff < 1.01
    assert core.weighted_beta_binomial([0.5] * 4, [False] * 4, a, b).n_eff == pytest.approx(4)
    with pytest.raises(ValueError):
        core.weighted_beta_binomial([1.0], [True, False], a, b)


def test_weight_similarity_and_prior() -> None:
    assert core.weight(0, 5000) == 1.0
    assert core.weight(5000, 5000) == pytest.approx(math.exp(-0.5))
    assert core.weight(0, 5000, similarity=0.75, recency=0.5) == pytest.approx(0.375)
    with pytest.raises(ValueError):
        core.weight(10, 0)
    ctx = core.Context(8.5, "KCl-polymer", "development")
    assert core.similarity(ctx, core.Context(8.5, "kcl-polymer", "development")) == 1.0
    assert core.similarity(ctx, core.Context(12.25, "KCl-polymer", None)) == 0.75
    assert core.similarity(ctx, core.Context(12.25, "water-based", "exploration")) == pytest.approx(
        0.75 * 0.8 * 0.9
    )
    assert core.similarity(core.Context(), core.Context(12.25, "water-based", "x")) == 1.0
    assert core.MIN_SIMILARITY == 0.5
    a, b = core.prior_params(0.0)  # clamped: one offset can never read as 0%
    assert a == pytest.approx(2 * core.MIN_BASE_RATE) and a + b == core.PRIOR_STRENGTH


@given(
    st.lists(st.tuples(st.floats(0.01, 1.0), st.booleans()), min_size=1, max_size=30),
    st.floats(0.0, 1.0),
)
def test_estimate_shrinks_between_prior_and_offsets(
    offsets: list[tuple[float, bool]], base_rate: float
) -> None:
    a, b = core.prior_params(base_rate)
    w = [o[0] for o in offsets]
    y = [o[1] for o in offsets]
    post = core.weighted_beta_binomial(w, y, a, b)
    observed = sum(wi for wi, yi in offsets if yi) / sum(w)
    prior_mean = a / (a + b)
    assert min(observed, prior_mean) - 1e-9 <= post.probability <= max(observed, prior_mean) + 1e-9
    assert 0 <= post.ci90_low <= post.probability <= post.ci90_high <= 1
    assert 1 - 1e-9 <= post.n_eff <= len(offsets) + 1e-9
