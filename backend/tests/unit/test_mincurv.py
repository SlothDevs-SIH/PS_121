"""Minimum curvature is exact for circular arcs and straight lines — test against closed forms."""

import math

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.geo.mincurv import (
    directional_stations,
    interpolate_at_md,
    minimum_curvature,
    vertical_stations,
)


def test_vertical_well_tvd_equals_md() -> None:
    md, inc, azi = vertical_stations(3000)
    t = minimum_curvature(md, inc, azi)
    assert np.allclose(t.tvd, md)
    assert np.allclose(t.north, 0) and np.allclose(t.east, 0)
    assert np.allclose(t.dls, 0)


def test_straight_inclined_hole() -> None:
    md = np.array([0.0, 100.0, 1000.0])
    inc = np.array([30.0, 30.0, 30.0])
    azi = np.array([45.0, 45.0, 45.0])
    t = minimum_curvature(md, inc, azi)
    horiz = 1000 * math.sin(math.radians(30))
    assert t.tvd[-1] == pytest.approx(1000 * math.cos(math.radians(30)))
    assert t.north[-1] == pytest.approx(horiz * math.cos(math.radians(45)))
    assert t.east[-1] == pytest.approx(horiz * math.sin(math.radians(45)))


@pytest.mark.parametrize("build_rate", [1.0, 2.5, 4.0])
def test_circular_build_arc_matches_closed_form(build_rate: float) -> None:
    kop, azimuth = 600.0, 120.0
    md, inc, azi = directional_stations(
        2000, kop, build_rate, max_inc_deg=90, azimuth_deg=azimuth, step_m=30
    )
    t = minimum_curvature(md, inc, azi)
    radius = 30 * 180 / (math.pi * build_rate)
    for k in range(len(md)):
        if inc[k] >= 90 or md[k] < kop:
            continue
        i = math.radians(inc[k])
        # Exact only where both neighbouring stations lie on the arc; skip the station
        # straddling the kick-off point.
        if md[k] - 30 < kop and md[k] != kop:
            continue
        assert t.tvd[k] == pytest.approx(kop + radius * math.sin(i), abs=1e-6)
        disp = radius * (1 - math.cos(i))
        assert t.north[k] == pytest.approx(disp * math.cos(math.radians(azimuth)), abs=1e-6)
        assert t.east[k] == pytest.approx(disp * math.sin(math.radians(azimuth)), abs=1e-6)
        if md[k] > kop + 30:
            assert t.dls[k] == pytest.approx(build_rate, rel=1e-9)


def test_md_at_tvd_and_position_interpolation() -> None:
    md, inc, azi = directional_stations(3000, 800, 2.0, 35, 90)
    t = minimum_curvature(md, inc, azi)
    target = 2000.0
    m = t.md_at_tvd(target)
    assert m is not None
    assert t.position_at_md(m)[2] == pytest.approx(target, abs=1e-6)
    assert t.md_at_tvd(10_000) is None


def test_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        minimum_curvature([0, 10, 5], [0, 0, 0], [0, 0, 0])
    with pytest.raises(ValueError):
        minimum_curvature([0, 10], [0, 200], [0, 0])


@given(
    st.floats(min_value=0, max_value=80),
    st.floats(min_value=0, max_value=359.9),
    st.floats(min_value=100, max_value=5000),
)
def test_tvd_never_exceeds_md_and_path_length_is_md(inc: float, az: float, td: float) -> None:
    t = minimum_curvature([0.0, td], [inc, inc], [az, az])
    assert t.tvd[-1] <= td + 1e-6
    length = math.sqrt(t.north[-1] ** 2 + t.east[-1] ** 2 + (t.tvd[-1] - t.tvd[0]) ** 2)
    assert length == pytest.approx(td, rel=1e-9)


@pytest.mark.parametrize("build_rate", [1.5, 3.0])
def test_interpolation_lies_exactly_on_the_arc(build_rate: float) -> None:
    kop, azimuth = 600.0, 60.0
    md, inc, azi = directional_stations(2000, kop, build_rate, 80, azimuth, step_m=30)
    t = minimum_curvature(md, inc, azi)
    radius = 30 * 180 / (math.pi * build_rate)
    for m in (645.0, 700.3, 1111.1):  # between stations, on the build arc
        n, e, tvd, i_deg, a_deg = interpolate_at_md(t, m)
        i = math.radians((m - kop) * build_rate / 30)
        assert i_deg == pytest.approx(math.degrees(i), abs=1e-6)
        assert a_deg == pytest.approx(azimuth, abs=1e-6)
        assert tvd == pytest.approx(kop + radius * math.sin(i), abs=1e-6)
        disp = radius * (1 - math.cos(i))
        assert n == pytest.approx(disp * math.cos(math.radians(azimuth)), abs=1e-6)
        assert e == pytest.approx(disp * math.sin(math.radians(azimuth)), abs=1e-6)


def test_interpolation_at_stations_and_out_of_range() -> None:
    md, inc, azi = vertical_stations(1000)
    t = minimum_curvature(md, inc, azi)
    assert interpolate_at_md(t, 300.0)[2] == pytest.approx(300.0)
    assert interpolate_at_md(t, 1000.0)[2] == pytest.approx(1000.0)
    with pytest.raises(ValueError):
        interpolate_at_md(t, 1000.5)
