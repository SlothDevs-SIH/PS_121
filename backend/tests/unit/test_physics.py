"""S7c physics indicators against hand-computed textbook values."""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core import units
from app.physics import indicators as ph


def test_d_exponent_matches_oilfield_formula() -> None:
    # 30 ft/h, 100 rpm, 20,000 lbf on an 8.5 in bit (worked by hand in oilfield units).
    rop = units.ft_to_m(30)
    wob = 20_000 / ph.KN_TO_LBF
    expected = math.log10(30 / 6000) / math.log10(12 * 20_000 / (1e6 * 8.5))
    assert ph.d_exponent(rop, 100, wob, 8.5) == pytest.approx(expected, rel=1e-9)
    assert 1.0 < expected < 2.5


def test_dc_and_eaton() -> None:
    assert ph.dc_exponent(1.6, 1.03, 1.30) == pytest.approx(1.6 * 1.03 / 1.30)
    tvd = 3000.0
    s = ph.hydrostatic_kpa(2.31, tvd)  # ~1.0 psi/ft overburden
    pn = ph.hydrostatic_kpa(1.03, tvd)
    # dc on trend → normal pressure; dc below trend → overpressure.
    assert ph.eaton_pore_pressure_kpa(s, pn, 1.4, 1.4) == pytest.approx(pn)
    assert ph.eaton_pore_pressure_kpa(s, pn, 1.1, 1.4) > pn


def test_ecd_si_equals_oilfield_form() -> None:
    mw, dp_psi, tvd_ft = 10.0, 300.0, 10_000.0  # ppg, psi, ft
    oilfield = mw + dp_psi / (0.052 * tvd_ft)
    si = ph.ecd_sg(units.ppg_to_sg(mw), units.psi_to_kpa(dp_psi), units.ft_to_m(tvd_ft))
    assert units.sg_to_ppg(si) == pytest.approx(oilfield, rel=2e-3)  # 0.052 is itself rounded


def test_mse_teale() -> None:
    wob_lbf, bit, rpm, t_ftlbf, rop_ft_h = 30_000, 8.5, 120, 10_000, 50
    area = math.pi * bit**2 / 4
    psi = wob_lbf / area + 120 * math.pi * rpm * t_ftlbf / (area * rop_ft_h)
    got = ph.mse_kpa(
        wob_lbf / ph.KN_TO_LBF, t_ftlbf / ph.KNM_TO_FTLBF, rpm, units.ft_to_m(rop_ft_h), bit
    )
    assert got == pytest.approx(units.psi_to_kpa(psi), rel=1e-9)


@given(
    st.floats(1, 100), st.floats(40, 200), st.floats(20, 300), st.sampled_from([6.0, 8.5, 12.25])
)
def test_mse_decreases_as_rop_rises(rop: float, rpm: float, wob: float, bit: float) -> None:
    assert ph.mse_kpa(wob, 20, rpm, rop * 1.5, bit) < ph.mse_kpa(wob, 20, rpm, rop, bit)


def test_kick_and_loss_indicators() -> None:
    assert ph.pit_gain_m3([50, 49.5, 49.8, 52.0]) == pytest.approx(2.5)
    assert ph.flow_imbalance_pct(2000, 2200) == pytest.approx(10)
    assert ph.flow_imbalance_pct(2000, 1500) == pytest.approx(-25)
    assert ph.flow_imbalance_pct(0, 100) == 0


def test_kick_and_loss_rule_flags() -> None:
    kick = ph.kick_loss_flags(12, -6, 1.2)
    assert kick == [
        "kick: flow out up with constant pumps",
        "kick: SPP down with flow out up",
        "kick: pit gain over threshold",
    ]
    loss = ph.kick_loss_flags(-20, -5, -1.0)
    assert [f.split(":")[0] for f in loss] == ["loss", "loss", "loss"]
    assert ph.kick_loss_flags(2, -1, 0.3) == []  # within tolerances: no flag
    assert units.m3_to_bbl(ph.PIT_THRESHOLD_M3) == pytest.approx(5)


def test_drilling_break() -> None:
    steady = [10.0] * 10
    assert ph.drilling_break([*steady, 25.0])
    assert not ph.drilling_break([*steady, 15.0])
    assert not ph.drilling_break([25.0])  # not enough history


def test_torque_baseline_is_per_rig_state() -> None:
    # Drilling torque ~10 kN.m, reaming ~20: a state-blind baseline would flag every switch.
    states = ["drill", "ream"] * 20 + ["drill"]
    torque = [10.0, 20.0] * 20 + [13.0]
    per_state = ph.baseline_deviation_pct(torque, window=10, states=states)
    assert per_state[:9] == [None] * 9  # half a window of baseline per state first
    assert all(d == pytest.approx(0) for d in per_state[10:-1])
    assert per_state[-1] == pytest.approx(30)
    blind = ph.baseline_deviation_pct(torque, window=10)
    assert max(abs(d) for d in blind if d is not None) >= 30


def test_torque_against_offsets_and_overpull_trend() -> None:
    assert ph.offset_deviation_pct(15, [10, 12, 9]) == pytest.approx(50)
    assert ph.offset_deviation_pct(15, []) is None
    assert ph.increasing_overpull_run([40, 30, 45, 60, 80]) == 4
    assert ph.increasing_overpull_run([40, 60, 60]) == 1
    assert ph.increasing_overpull_run([]) == 0


def test_threshold_detector_hysteresis() -> None:
    det = ph.ThresholdDetector(on=10, off=6, min_consecutive=2)
    series = [5, 11, 9, 11, 12, 9, 7, 5.5, 11, 11]
    events = [c for i, v in enumerate(series) if (c := det.update(i, v))]
    # One spike doesn't raise; staying above 'off' (9, 7) doesn't clear.
    assert [(c.index, c.kind) for c in events] == [(4, "raised"), (7, "cleared"), (9, "raised")]
    with pytest.raises(ValueError):
        ph.ThresholdDetector(on=5, off=6)


def test_cementing_risk_levels() -> None:
    assert ph.cementing_risk(1.50, [1.45, 1.60], 2, 4).level == "high"
    med = ph.cementing_risk(1.42, [1.45], 0, 4)
    assert med.level == "medium" and "within 0.05" in med.flags[0]
    assert ph.cementing_risk(1.30, [1.45], 0, 5) == ph.CementingRisk("low", [])


def test_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        ph.d_exponent(0, 100, 50, 8.5)
    with pytest.raises(ValueError):
        ph.ecd_sg(1.2, 100, 0)
