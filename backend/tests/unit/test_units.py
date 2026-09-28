import math

from hypothesis import given
from hypothesis import strategies as st

from app.core import units

finite = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False)


def test_reference_values() -> None:
    assert math.isclose(units.ft_to_m(1000), 304.8)
    assert math.isclose(units.sg_to_ppg(1.0), 8.345)
    assert math.isclose(units.ppg_to_psi_per_ft(10.0), 0.52)
    assert math.isclose(units.bbl_to_m3(100), 15.8987)
    assert math.isclose(units.psi_to_kpa(1.0), 6.894757)
    assert math.isclose(units.sg_to_kpa_per_m(1.0), 9.80665)
    assert math.isclose(units.klbf_to_kn(1.0), 4.448222)
    assert math.isclose(units.kftlbf_to_knm(1.0), 1.355818)
    assert math.isclose(units.usgpm_to_lpm(1.0), 3.785412)


@given(finite)
def test_round_trips(x: float) -> None:
    assert math.isclose(units.m_to_ft(units.ft_to_m(x)), x, rel_tol=1e-12, abs_tol=1e-9)
    assert math.isclose(units.sg_to_ppg(units.ppg_to_sg(x)), x, rel_tol=1e-12, abs_tol=1e-9)
    assert math.isclose(units.m3_to_bbl(units.bbl_to_m3(x)), x, rel_tol=1e-12, abs_tol=1e-9)
    assert math.isclose(units.kpa_to_psi(units.psi_to_kpa(x)), x, rel_tol=1e-12, abs_tol=1e-9)


def test_gradient_conventions_agree() -> None:
    # 1 SG expressed as psi/ft (via ppg) and as kPa/m must describe the same gradient.
    psi_per_ft = units.ppg_to_psi_per_ft(units.sg_to_ppg(1.0))
    kpa_per_m = units.psi_to_kpa(psi_per_ft) / units.ft_to_m(1.0)
    assert math.isclose(kpa_per_m, units.sg_to_kpa_per_m(1.0), rel_tol=2e-3)
