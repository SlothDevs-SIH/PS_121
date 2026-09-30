"""Stream data-quality checks (Part 7, V-B31): flat-lined sensors, unit switches at the
source and impossible values are flagged, and a flagged flow channel cannot raise a kick."""

from datetime import timedelta

import numpy as np

from app.stream.quality import FLATLINE_SAMPLES, JUMP_RECENT, QualityMonitor
from app.stream.scorer import WellScorer
from app.synthetic import realtime as rt
from tests.unit.test_scorer import T0, _ctx


def _feed(m: QualityMonitor, series: list[dict[str, float | None]], state: str = "DRILLING"):
    return [m.update(v, state) for v in series]


def test_flatline_only_where_the_channel_must_move() -> None:
    m = QualityMonitor()
    rng = np.random.default_rng(1)
    flags = _feed(
        m,
        [{"torque_knm": 12.5, "rpm": 120.0} for _ in range(FLATLINE_SAMPLES)]
        + [{"torque_knm": float(12 + rng.random())}],
    )
    assert flags[FLATLINE_SAMPLES - 2] == {}
    assert flags[FLATLINE_SAMPLES - 1] == {"torque_knm": "flatline"}  # 10 min frozen
    assert flags[-1] == {}  # moves again: clear
    # In slips the torque is legitimately constant.
    m2 = QualityMonitor()
    assert _feed(m2, [{"torque_knm": 0.0}] * FLATLINE_SAMPLES, "IN_SLIPS")[-1] == {}


def test_a_step_by_a_conversion_factor_is_a_unit_jump_until_it_returns() -> None:
    m = QualityMonitor()
    rng = np.random.default_rng(2)
    base = [2000 + rng.normal(0, 5) for _ in range(40)]
    in_psi = [x / 6.894757 for x in [2000.0] * 20]  # the source switched kPa → psi
    back = [2000.0] * 10
    flags = _feed(m, [{"spp_kpa": v} for v in base + in_psi + back])
    assert all(f == {} for f in flags[: 40 + JUMP_RECENT - 1])
    assert flags[40 + JUMP_RECENT - 1] == {"spp_kpa": "unit_jump"}
    assert all(f == {"spp_kpa": "unit_jump"} for f in flags[40 + JUMP_RECENT : 60])
    # Back in the mapped unit: cleared once the recent median agrees (3 samples here), and
    # the step back is not mistaken for a new jump.
    assert flags[62] == {"spp_kpa": "unit_jump"} and flags[63:] == [{}] * 7


def test_an_ordinary_level_change_is_not_a_unit_jump() -> None:
    m = QualityMonitor()
    # Pump rate raised 1500 → 2400 L/min: a real change, not a conversion factor.
    flags = _feed(m, [{"flow_in_lpm": 1500.0}] * 40 + [{"flow_in_lpm": 2400.0}] * 20, "CIRCULATING")
    assert all("flow_in_lpm" not in f or f["flow_in_lpm"] == "flatline" for f in flags)
    assert not any(f.get("flow_in_lpm") == "unit_jump" for f in flags)


def test_impossible_values_are_out_of_range() -> None:
    m = QualityMonitor()
    assert m.update({"flow_out_lpm": -500.0, "gas_pct": 140.0, "rpm": 90.0}, "DRILLING") == {
        "flow_out_lpm": "out_of_range",
        "gas_pct": "out_of_range",
    }


def test_a_unit_switch_on_flow_out_does_not_raise_a_kick() -> None:
    """Flow-out suddenly x3.785 (L/min → gpm the wrong way round) looks like a huge gain in
    returns; with the check it is bad data, not a kick."""
    top = 2275.0
    ep = rt.replay_episode(3, "W", 2214.0, T0, top, 8.5, 1.42)
    scorer = WellScorer(_ctx(top), bundle=None, library=[], tau=None)
    kicks, frames_flagged = [], 0
    for i in range(400):
        values: dict[str, float | None] = {c: float(ep.data[c][i]) for c in rt.CHANNELS}
        if i >= 300 and values["flow_out_lpm"]:
            values["flow_out_lpm"] = values["flow_out_lpm"] * 3.785412
        frame, cands = scorer.push(T0 + timedelta(seconds=rt.DT_S * i), values)
        kicks += [c for c in cands if c.alert_type == "PHYSICS" and c.event_type == "KICK"]
        frames_flagged += frame.quality.get("flow_out_lpm") == "unit_jump"
        assert "quality" in frame.to_json()
    assert frames_flagged > 0
    assert kicks == []
