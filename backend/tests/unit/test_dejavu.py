"""S7d Déjà Vu maths: MASS equals brute force, banded DTW, and search behaviour."""

from datetime import datetime

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.risk import dejavu as dv
from app.synthetic import realtime as rt


def _znorm_dist(a: np.ndarray, b: np.ndarray, noise: float) -> float:
    za = (a - a.mean()) / max(float(a.std()), noise)
    zb = (b - b.mean()) / max(float(b.std()), noise)
    return float(np.sqrt(np.sum((za - zb) ** 2)))


@settings(max_examples=25, deadline=None)
@given(st.integers(0, 10_000))
def test_mass_equals_brute_force(seed: int) -> None:
    rng = np.random.default_rng(seed)
    series = np.cumsum(rng.normal(size=120))
    query = np.cumsum(rng.normal(size=30))
    got = dv.mass(query, series, noise=1e-6)
    want = [_znorm_dist(query, series[k : k + 30], 1e-6) for k in range(91)]
    assert got == pytest.approx(want, abs=1e-6)


def test_mass_finds_an_embedded_query() -> None:
    rng = np.random.default_rng(0)
    series = rng.normal(size=200)
    query = series[70:110] * 3 + 5  # z-normalisation ignores scale and offset
    assert int(np.argmin(dv.mass(query, series, 1e-6))) == 70


def test_banded_dtw() -> None:
    a = np.sin(np.linspace(0, 6, 40))
    assert dv.dtw(a, a, 4) == 0.0
    shifted = np.sin(np.linspace(0, 6, 40) - 0.3)
    assert dv.dtw(a, shifted, 4) < float(np.abs(a - shifted).sum())  # warping helps
    assert dv.dtw(a, shifted, 0) == pytest.approx(float(np.abs(a - shifted).sum()))


def _library_from(eps: list[rt.Episode]) -> list[dv.Signature]:
    out = []
    for i, ep in enumerate(eps):
        pre = {c: v[rt.PRE_STEPS - dv.SIGNATURE_STEPS : rt.PRE_STEPS] for c, v in ep.data.items()}
        share = float(np.mean(pre["wob_kn"] > 10))
        et = ep.planted[0].event_type
        out.append(dv.Signature(i, et, dv.prepare(pre), share, 8.5, well_id=i))
    return out


def _query(ep: rt.Episode, end: int) -> tuple[dict[str, np.ndarray], float]:
    w = {c: v[end - dv.QUERY_STEPS : end] for c, v in ep.data.items()}
    return dv.prepare(w), float(np.mean(w["wob_kn"] > 10))


def test_a_precursor_matches_its_own_kind_and_a_quiet_window_does_not() -> None:
    t0 = datetime(2020, 1, 1)
    lib = _library_from(
        [
            rt.event_episode(np.random.default_rng(s), "W", "E", et, 2500, t0, "Tipam", 8.5, 1.3)
            for s, et in enumerate(["LOSS", "KICK", "BALLING", "LOSS", "KICK", "BALLING"])
        ]
    )
    other = rt.event_episode(np.random.default_rng(99), "X", "E", "KICK", 2500, t0, "T", 8.5, 1.3)
    q, share = _query(other, rt.PRE_STEPS)
    # tau = 1.0 is about what calibration on precursor-free windows gives (~1.07).
    best = dv.search(q, lib, tau=1.0, drilling_share=share, hole_size_in=8.5)[0]
    assert best.signature.event_type == "KICK"
    assert best.distance < 0.35  # 0 = the same change, ~1 = unrelated
    assert best.similarity == pytest.approx(np.exp(-best.distance))
    assert 0 <= best.minutes_before_event <= 40
    quiet = rt.normal_episode(np.random.default_rng(7), "Y", 2500, t0, 8.5, 1.3)
    qq, qshare = _query(quiet, 600)
    calm = dv.search(qq, lib, tau=1.0, drilling_share=qshare, hole_size_in=8.5)[0]
    # Measured: 0.36 vs 0.25. Closer, not dramatically so (alert recall is ~0.5, see eval).
    assert calm.distance > 1.3 * best.distance


def test_context_gate_and_own_well_exclusion() -> None:
    t0 = datetime(2020, 1, 1)
    ep = rt.event_episode(np.random.default_rng(1), "W", "E", "LOSS", 2500, t0, "T", 8.5, 1.3)
    lib = _library_from([ep])
    q, share = _query(ep, rt.PRE_STEPS)
    assert dv.search(q, lib, 0.3, share, 8.5, exclude_well=0) == []
    assert dv.search(q, lib, 0.3, share, 12.25) == []  # other hole-size class
    assert dv.search(q, lib, 0.3, share - 0.5, 8.5) == []  # other rig-state mix


def test_tau_calibration() -> None:
    tau = dv.calibrate_tau([0.5] * 99 + [0.1], false_match_rate=0.01)
    assert np.exp(-0.1 / tau) >= dv.ALERT_SIMILARITY - 1e-6
