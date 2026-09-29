"""Rig-state detection (S7b first step): a rules state machine over the drilling channels.

Every downstream signal is conditioned on it: the torque baseline is kept per rig state,
classifiers score drilling time, and an off-bottom pick-up is where overpull shows. Rules,
not a model, so a driller can check each decision:

- IN_SLIPS: hookload near the travelling-block weight with the pumps off.
- DRILLING: on bottom (bit within 0.5 m of hole depth) with weight on bit.
- STUCK: no weight on bit, not moving, not rotating, with the hookload well above the
  string weight (the driller is pulling on it) for 2 minutes.
- REAMING: off bottom, moving, pumping and rotating.
- TRIP_IN / TRIP_OUT: off bottom, moving without pumping.
- CIRCULATING: off bottom, pumping, not moving.
- STATIONARY: everything else.
"""

from dataclasses import dataclass, field

import numpy as np

ON_BOTTOM_M = 0.5
MOVING_M_PER_S = 0.01  # 0.6 m/min of block travel
PUMPS_LPM = 200.0
ROTATING_RPM = 20.0
WOB_KN = 10.0
SLIPS_HOOKLOAD_KN = 260.0  # block + top drive; the string hangs in the slips
OVERPULL_KN = 150.0
STUCK_STEPS = 12  # 2 min at 10 s


@dataclass
class RigStateMachine:
    """Streaming classifier: feed samples in time order, one call per sample."""

    dt_s: float = 10.0
    _prev_bit: float | None = None
    _still_pull: int = 0
    _string_wt: float | None = None  # hookload seen while drilling + WOB (an estimate)
    history: list[str] = field(default_factory=list)

    def update(
        self,
        bit_depth: float,
        hole_depth: float,
        hookload: float,
        wob: float,
        rpm: float,
        flow_in: float,
    ) -> str:
        speed = 0.0 if self._prev_bit is None else (bit_depth - self._prev_bit) / self.dt_s
        self._prev_bit = bit_depth
        on_bottom = hole_depth - bit_depth <= ON_BOTTOM_M
        moving = abs(speed) >= MOVING_M_PER_S
        pumps = flow_in >= PUMPS_LPM
        rotating = rpm >= ROTATING_RPM

        if on_bottom and wob >= WOB_KN:
            state = "DRILLING"
            est = hookload + wob
            self._string_wt = (
                est if self._string_wt is None else 0.98 * self._string_wt + 0.02 * est
            )
        elif hookload <= SLIPS_HOOKLOAD_KN and not pumps:
            state = "IN_SLIPS"
        elif moving:
            state = "REAMING" if pumps and rotating else ("TRIP_OUT" if speed < 0 else "TRIP_IN")
        elif pumps:
            state = "CIRCULATING"
        else:
            state = "STATIONARY"

        pulling = (
            self._string_wt is not None
            and hookload >= self._string_wt + OVERPULL_KN
            and not moving
            and not rotating
            and wob < WOB_KN
        )
        self._still_pull = self._still_pull + 1 if pulling else 0
        if self._still_pull >= STUCK_STEPS:
            state = "STUCK"
        self.history.append(state)
        return state


def classify(data: dict[str, np.ndarray], dt_s: float = 10.0) -> list[str]:
    """Rig state of every sample of a window (canonical channel arrays)."""
    m = RigStateMachine(dt_s=dt_s)
    return [
        m.update(
            float(data["bit_depth_m"][i]),
            float(data["hole_depth_m"][i]),
            float(data["hookload_kn"][i]),
            float(data["wob_kn"][i]),
            float(data["rpm"][i]),
            float(data["flow_in_lpm"][i]),
        )
        for i in range(len(data["bit_depth_m"]))
    ]
