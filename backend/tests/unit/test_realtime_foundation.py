"""B4 foundations: the synthetic real-time simulator plants the precursors it claims, and
the rig-state machine reads operations the way a driller would."""

from datetime import datetime

import numpy as np
import pytest

from app.risk.rigstate import RigStateMachine, classify
from app.synthetic import realtime as rt

T0 = datetime(2020, 1, 1, 12)


def _episode(event_type: str, seed: int = 3) -> rt.Episode:
    return rt.event_episode(
        np.random.default_rng(seed), "W", "E1", event_type, 2500, T0, "Tipam", 8.5, 1.3
    )


def _drilling_mean(ep: rt.Episode, channel: str, sl: slice) -> float:
    d = ep.data
    on = d["wob_kn"][sl] > 0
    return float(np.mean(d[channel][sl][on]))


def _imbalance_pct(ep: rt.Episode, sl: slice) -> float:
    fi, fo = ep.data["flow_in_lpm"][sl], ep.data["flow_out_lpm"][sl]
    pumping = fi > 0
    return float(np.mean((fo[pumping] - fi[pumping]) / fi[pumping] * 100))


EARLY = slice(0, 300)
LATE = slice(rt.PRE_STEPS - 120, rt.PRE_STEPS)


def test_simulation_is_deterministic_and_complete() -> None:
    a, b = _episode("LOSS"), _episode("LOSS")
    assert set(a.data) == set(rt.CHANNELS)
    assert all(np.array_equal(a.data[c], b.data[c]) for c in rt.CHANNELS)
    assert a.n == rt.PRE_STEPS + rt.POST_STEPS
    assert np.all(np.diff(a.data["hole_depth_m"]) >= 0)  # the hole never gets shallower
    assert abs(a.data["hole_depth_m"][rt.PRE_STEPS] - 2500) < 60  # reaches the event depth


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_planted_precursors_show_before_the_event(seed: int) -> None:
    loss = _episode("LOSS", seed)
    assert _imbalance_pct(loss, LATE) < _imbalance_pct(loss, EARLY) - 3
    assert loss.data["pit_volume_m3"][rt.PRE_STEPS] < loss.data["pit_volume_m3"][300] - 1
    kick = _episode("KICK", seed)
    assert _imbalance_pct(kick, LATE) > _imbalance_pct(kick, EARLY) + 3
    assert _drilling_mean(kick, "gas_pct", LATE) > 2 * _drilling_mean(kick, "gas_pct", EARLY)
    stuck = _episode("STUCK", seed)
    assert _drilling_mean(stuck, "torque_knm", LATE) > 1.1 * _drilling_mean(
        stuck, "torque_knm", EARLY
    )
    balling = _episode("BALLING", seed)
    assert _drilling_mean(balling, "rop_m_h", LATE) < 0.8 * _drilling_mean(
        balling, "rop_m_h", EARLY
    )
    normal = rt.normal_episode(np.random.default_rng(seed), "W", 2500, T0, 8.5, 1.3)
    assert abs(_imbalance_pct(normal, LATE) - _imbalance_pct(normal, EARLY)) < 2


def test_rig_states_of_a_simulated_stuck_pipe() -> None:
    ep = rt.event_episode(
        np.random.default_rng(5), "W", "E1", "STUCK", 2400, T0, "Barail", 12.25, 1.3
    )  # a seed whose window includes a connection
    states = classify(ep.data)
    before = states[: rt.PRE_STEPS]
    assert before.count("DRILLING") / len(before) > 0.8
    assert "IN_SLIPS" in before  # connections
    assert "STUCK" not in before
    after = states[rt.PRE_STEPS :]
    assert after.index("STUCK") <= 14  # declared within ~2 min of sticking


def test_rig_state_rules() -> None:
    m = RigStateMachine()
    assert m.update(1000, 1000, 600, 80, 120, 2000) == "DRILLING"
    assert m.update(1000, 1000, 600, 80, 120, 2000) == "DRILLING"
    assert m.update(996, 1000, 700, 0, 120, 2000) == "REAMING"  # pulling up while rotating
    assert m.update(996, 1000, 700, 0, 0, 2000) == "CIRCULATING"
    assert m.update(996, 1000, 180, 0, 0, 0) == "IN_SLIPS"
    assert m.update(990, 1000, 650, 0, 0, 0) == "TRIP_OUT"
    assert m.update(995, 1000, 650, 0, 0, 0) == "TRIP_IN"
    assert m.update(995, 1000, 650, 0, 0, 0) == "STATIONARY"
