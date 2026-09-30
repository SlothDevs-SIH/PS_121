"""Per-channel data-quality checks on the live stream (Part 7, V-B31).

The mapping step already flags values that are missing, unreadable or unmapped. Real rig
feeds also fail in ways that still deliver numbers:

- **flatline**: a channel that must move while the rig is working (torque while drilling,
  SPP while pumping…) repeats exactly the same value for ``FLATLINE_SAMPLES`` (a frozen
  sensor or a stuck OPC tag);
- **unit_jump**: the level steps abruptly by a known unit-conversion factor (kPa↔psi,
  L/min↔gpm, m³↔bbl, m↔ft, kN↔klbf, kN·m↔kft·lbf) and stays there: someone changed the
  unit at the source, so the numbers are no longer what the mapping says;
- **out_of_range**: physically impossible for the channel (negative flow, SPP above
  100 MPa…).

Flags are advisory for the display, and protective for alerts: the physics rules skip a
flagged flow or pit channel instead of raising a false kick or loss on bad data.
"""

from collections import deque
from dataclasses import dataclass, field

import numpy as np

FLATLINE_SAMPLES = 60  # 10 min at 10 s
JUMP_RECENT = 6  # samples after the step that must agree
JUMP_BASELINE = 30  # samples before the step
JUMP_TOLERANCE = 0.03  # |ratio / factor - 1|
RECOVER_TOLERANCE = 0.10

# Unit-conversion factors a channel can plausibly jump by (either direction).
FACTORS: dict[str, tuple[float, ...]] = {
    "spp_kpa": (6.894757, 100.0),  # psi, bar
    "flow_in_lpm": (3.785412, 1000.0 / 60.0),  # gpm, m3/min
    "flow_out_lpm": (3.785412, 1000.0 / 60.0),
    "pit_volume_m3": (6.289811,),  # bbl
    "hookload_kn": (4.448222, 9.80665),  # klbf, tonne-force
    "wob_kn": (4.448222, 9.80665),
    "torque_knm": (1.355818,),  # kft.lbf
    "bit_depth_m": (3.28084,),  # ft
    "hole_depth_m": (3.28084,),
    "rop_m_h": (3.28084,),
}

# (low, high) physical limits in canonical units.
RANGES: dict[str, tuple[float, float]] = {
    "bit_depth_m": (-10.0, 12000.0),
    "hole_depth_m": (-10.0, 12000.0),
    "hookload_kn": (-50.0, 10000.0),
    "wob_kn": (-50.0, 2000.0),
    "rpm": (-5.0, 400.0),
    "torque_knm": (-5.0, 150.0),
    "spp_kpa": (-100.0, 100000.0),
    "flow_in_lpm": (-10.0, 20000.0),
    "flow_out_lpm": (-10.0, 20000.0),
    "pit_volume_m3": (0.0, 2000.0),
    "rop_m_h": (-1.0, 300.0),
    "gas_pct": (0.0, 100.0),
}

# Channels that must vary, and the rig states in which they must.
MOVING = {
    "torque_knm": {"DRILLING", "REAMING"},
    "rop_m_h": {"DRILLING"},
    "wob_kn": {"DRILLING"},
    "spp_kpa": {"DRILLING", "REAMING", "CIRCULATING"},
    "flow_in_lpm": {"DRILLING", "REAMING", "CIRCULATING"},
    "flow_out_lpm": {"DRILLING", "REAMING", "CIRCULATING"},
    "hookload_kn": {"DRILLING", "REAMING", "TRIP_IN", "TRIP_OUT"},
}

# Flags that make a channel unfit for the physics alert rules.
UNFIT = frozenset({"unit_jump", "out_of_range", "flatline"})


@dataclass
class _Chan:
    values: deque[float] = field(default_factory=lambda: deque(maxlen=JUMP_BASELINE + JUMP_RECENT))
    same: int = 0  # consecutive identical values
    last: float | None = None
    jump: tuple[float, float] | None = None  # (baseline level, factor) while jumped


@dataclass
class QualityMonitor:
    chans: dict[str, _Chan] = field(default_factory=dict)

    def update(self, values: dict[str, float | None], rig_state: str) -> dict[str, str]:
        """Flags for this sample (channel → flag); channels that are fine are absent."""
        flags: dict[str, str] = {}
        for ch, v in values.items():
            if v is None:
                continue
            c = self.chans.setdefault(ch, _Chan())
            lo_hi = RANGES.get(ch)
            if lo_hi and not lo_hi[0] <= v <= lo_hi[1]:
                flags[ch] = "out_of_range"
            c.same = c.same + 1 if c.last is not None and v == c.last else 0
            c.last = v
            c.values.append(v)
            if flag := self._jump(ch, c):
                flags.setdefault(ch, flag)
            states = MOVING.get(ch)
            if states and rig_state in states and c.same >= FLATLINE_SAMPLES - 1:
                flags.setdefault(ch, "flatline")
        return flags

    def _jump(self, ch: str, c: _Chan) -> str | None:
        factors = FACTORS.get(ch)
        if not factors:
            return None
        vals = np.asarray(c.values, dtype=float)
        recent = float(np.median(vals[-JUMP_RECENT:]))
        if c.jump is not None:
            base, _ = c.jump
            if base and abs(recent / base - 1) <= RECOVER_TOLERANCE:
                c.jump = None  # the source went back to the mapped unit:
                c.values.clear()  # the wrong-unit stretch is no baseline for the next step
                return None
            return "unit_jump"
        if len(vals) < JUMP_BASELINE + JUMP_RECENT:
            return None
        before = vals[:-JUMP_RECENT]
        after = vals[-JUMP_RECENT:]
        base = float(np.median(before))
        # Abrupt and settled: both sides steady, a single step between them.
        if abs(base) < 1e-6 or np.ptp(after) > 0.05 * abs(recent) + 1e-9:
            return None
        if np.ptp(before[-JUMP_RECENT:]) > 0.05 * abs(base) + 1e-9:
            return None
        ratio = recent / base
        for f in factors:
            for target in (f, 1 / f):
                if abs(ratio / target - 1) <= JUMP_TOLERANCE:
                    c.jump = (base, target)
                    return "unit_jump"
        return None
