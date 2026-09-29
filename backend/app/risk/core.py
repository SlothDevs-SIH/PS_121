"""Offset prior risk mathematics (master plan §Stage 7a).

For event type e and interval k of the subject well, each offset i that penetrated k has

    wᵢ = exp(−dᵢ² / 2σ²) × sᵢ × rᵢ      (distance, similarity, recency)
    P̂(e | k) = (Σ wᵢ·yᵢ + α) / (Σ wᵢ + α + β)

with α, β from the basin-wide base rate so one offset never reads as 0% or 100%. The
posterior is Beta(Σwy + α, Σw − Σwy + β): its 5–95% quantiles are the 90% credible
interval, and n_eff = (Σw)² / Σw² says how many offsets' worth of evidence there is.
"""

import math
from dataclasses import dataclass

from scipy.stats import beta

PRIOR_STRENGTH = 2.0  # α + β: the basin prior counts as two offsets' worth of evidence
# Floor (and 1 − ceiling) on the base rate: keeps α, β ≥ 0.02. Below α ≈ 0.014 a Beta is so
# skewed that its mean falls outside its own 5–95% interval (checked on a grid, and by the
# property test in tests/unit/test_risk_core.py), which would print as "P = 0.3%, CI 0–0.1%".
MIN_BASE_RATE = 0.01
# Similarity sᵢ (master plan: hole size / mud system / well type match, 0.5–1.0): each
# mismatch multiplies by its factor; an unknown value counts as a match.
HOLE_MISMATCH_SIMILARITY = 0.75
MUD_MISMATCH_SIMILARITY = 0.8
WELL_TYPE_MISMATCH_SIMILARITY = 0.9
MIN_SIMILARITY = 0.5


@dataclass(frozen=True)
class Posterior:
    probability: float
    ci90_low: float
    ci90_high: float
    n_eff: float


def weight(
    distance_m: float, sigma_m: float, similarity: float = 1.0, recency: float = 1.0
) -> float:
    if sigma_m <= 0:
        raise ValueError("sigma must be positive")
    return math.exp(-(distance_m**2) / (2 * sigma_m**2)) * similarity * recency


def prior_params(base_rate: float, strength: float = PRIOR_STRENGTH) -> tuple[float, float]:
    p0 = min(max(base_rate, MIN_BASE_RATE), 1 - MIN_BASE_RATE)
    return strength * p0, strength * (1 - p0)


def weighted_beta_binomial(
    weights: list[float], outcomes: list[bool], alpha: float, beta_: float
) -> Posterior:
    if len(weights) != len(outcomes):
        raise ValueError("weights and outcomes differ in length")
    sw = sum(weights)
    swy = sum(w for w, y in zip(weights, outcomes, strict=True) if y)
    a, b = swy + alpha, sw - swy + beta_
    n_eff = sw**2 / sum(w * w for w in weights) if sw > 0 else 0.0
    return Posterior(
        probability=a / (a + b),
        ci90_low=float(beta.ppf(0.05, a, b)),
        ci90_high=float(beta.ppf(0.95, a, b)),
        n_eff=n_eff,
    )


@dataclass(frozen=True)
class Context:
    """What makes an offset's interval comparable with the subject's."""

    hole_in: float | None = None
    mud_type: str | None = None
    well_type: str | None = None


def _differs(a: str | None, b: str | None) -> bool:
    return bool(a and b and a.casefold() != b.casefold())


def similarity(subject: Context, offset: Context) -> float:
    s = 1.0
    if (
        subject.hole_in is not None
        and offset.hole_in is not None
        and abs(subject.hole_in - offset.hole_in) >= 0.01
    ):
        s *= HOLE_MISMATCH_SIMILARITY
    if _differs(subject.mud_type, offset.mud_type):
        s *= MUD_MISMATCH_SIMILARITY
    if _differs(subject.well_type, offset.well_type):
        s *= WELL_TYPE_MISMATCH_SIMILARITY
    return max(MIN_SIMILARITY, s)
