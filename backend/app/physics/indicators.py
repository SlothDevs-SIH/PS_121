"""S7c physics indicators: textbook formulas that need no training (master plan §Stage 7c).

Inputs are canonical SI (m, m/h, kN, kN.m, kPa, SG) and converted to each formula's native
oilfield units with app.core.units, so the published constants apply unchanged.
The real-time engine (B4) evaluates these on the live stream; the threshold detector with
hysteresis turns an indicator series into discrete crossings.
"""

import math
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import median

from app.core import units

KN_TO_LBF = 1000 / 4.4482216152605
KNM_TO_FTLBF = 1 / units.KFTLBF_TO_KNM * 1000  # kN.m → ft.lbf
PIT_THRESHOLD_M3 = units.bbl_to_m3(5)  # master plan: 5–10 bbl, configurable


def d_exponent(rop_m_h: float, rpm: float, wob_kn: float, bit_diameter_in: float) -> float:
    """Jorden & Shirley: d = log10(R / 60N) / log10(12W / (10^6 D)); R ft/h, W lbf, D in.

    Defined while drilling (R > 0, N > 0, W > 0); both logarithms are negative in the normal
    operating range, so d is positive (typically 1-2)."""
    if rop_m_h <= 0 or rpm <= 0 or wob_kn <= 0 or bit_diameter_in <= 0:
        raise ValueError("d-exponent needs positive ROP, RPM, WOB and bit diameter")
    r_ft_h = units.m_to_ft(rop_m_h)
    w_lbf = wob_kn * KN_TO_LBF
    num = math.log10(r_ft_h / (60.0 * rpm))
    den = math.log10(12.0 * w_lbf / (1e6 * bit_diameter_in))
    if den == 0:
        raise ValueError("d-exponent undefined when 12W = 10^6 D")
    return num / den


def dc_exponent(d: float, normal_gradient_sg: float, ecd_sg: float) -> float:
    """Corrected d-exponent: dc = d × (ρ_normal / ρ_ECD). A sustained drop below the normal
    compaction trend in shales indicates rising pore pressure."""
    if ecd_sg <= 0:
        raise ValueError("ECD must be positive")
    return d * normal_gradient_sg / ecd_sg


def eaton_pore_pressure_kpa(
    overburden_kpa: float, normal_kpa: float, dc_observed: float, dc_normal: float
) -> float:
    """Eaton (dc form, exponent 1.2): Pp = S − (S − Pn)·(dc_obs / dc_norm)^1.2.

    Only meaningful with an overburden estimate; callers must show that assumption."""
    if dc_normal <= 0 or dc_observed <= 0:
        raise ValueError("dc values must be positive")
    ratio: float = (dc_observed / dc_normal) ** 1.2
    return overburden_kpa - (overburden_kpa - normal_kpa) * ratio


def hydrostatic_kpa(density_sg: float, tvd_m: float) -> float:
    return units.sg_to_kpa_per_m(density_sg) * tvd_m


def ecd_sg(mw_sg: float, annular_pressure_loss_kpa: float, tvd_m: float) -> float:
    """ECD = MW + ΔP_annular / (gradient × TVD); the SI form of MW + ΔP/(0.052·TVD)."""
    if tvd_m <= 0:
        raise ValueError("TVD must be positive")
    return mw_sg + annular_pressure_loss_kpa / (units.KPA_PER_M_PER_SG * tvd_m)


def mse_kpa(
    wob_kn: float, torque_knm: float, rpm: float, rop_m_h: float, bit_diameter_in: float
) -> float:
    """Teale mechanical specific energy, MSE = WOB/A + 120·π·N·T/(A·ROP) in psi
    (WOB lbf, A in², N rpm, T ft·lbf, ROP ft/h), returned in kPa."""
    if rop_m_h <= 0 or bit_diameter_in <= 0:
        raise ValueError("MSE needs positive ROP and bit diameter")
    area_in2 = math.pi * bit_diameter_in**2 / 4
    wob_lbf = wob_kn * KN_TO_LBF
    torque_ftlbf = torque_knm * KNM_TO_FTLBF
    rop_ft_h = units.m_to_ft(rop_m_h)
    psi = wob_lbf / area_in2 + 120 * math.pi * rpm * torque_ftlbf / (area_in2 * rop_ft_h)
    return units.psi_to_kpa(psi)


def pit_gain_m3(pit_volumes_m3: list[float]) -> float:
    """Gain of the active pit system over a window (last − minimum so far)."""
    if not pit_volumes_m3:
        return 0.0
    return pit_volumes_m3[-1] - min(pit_volumes_m3)


def flow_imbalance_pct(flow_in_lpm: float, flow_out_lpm: float) -> float:
    """Return-flow excess (+, kick indicator) or deficit (−, loss indicator) in % of flow in."""
    if flow_in_lpm <= 0:
        return 0.0
    return 100.0 * (flow_out_lpm - flow_in_lpm) / flow_in_lpm


def kick_loss_flags(
    flow_out_change_pct: float,
    spp_change_pct: float,
    pit_change_m3: float,
    *,
    flow_tol_pct: float = 5.0,
    spp_tol_pct: float = 3.0,
    pit_threshold_m3: float = PIT_THRESHOLD_M3,
) -> list[str]:
    """Rule flags over one window with the pumps constant (master plan §Stage 7c).

    Kick: flow-out up, pit gain over the threshold, SPP down while flow-out rises.
    Loss: return flow down, pit loss over the threshold, SPP drop while returns fall."""
    flags: list[str] = []
    if flow_out_change_pct >= flow_tol_pct:
        flags.append("kick: flow out up with constant pumps")
        if spp_change_pct <= -spp_tol_pct:
            flags.append("kick: SPP down with flow out up")
    if pit_change_m3 >= pit_threshold_m3:
        flags.append("kick: pit gain over threshold")
    if flow_out_change_pct <= -flow_tol_pct:
        flags.append("loss: return flow down")
        if spp_change_pct <= -spp_tol_pct:
            flags.append("loss: SPP drop with returns down")
    if pit_change_m3 <= -pit_threshold_m3:
        flags.append("loss: pit volume loss over threshold")
    return flags


def drilling_break(rop_m_h: Sequence[float], window: int = 10, factor: float = 2.0) -> bool:
    """Sudden ROP increase: the latest ROP is at least `factor` × the median of the `window`
    samples before it. A kick indicator when it coincides with a flow-out gain."""
    if len(rop_m_h) <= window:
        return False
    base = median(rop_m_h[-window - 1 : -1])
    return base > 0 and rop_m_h[-1] >= factor * base


def baseline_deviation_pct(
    values: Sequence[float], window: int = 30, states: Sequence[str] | None = None
) -> list[float | None]:
    """Torque & drag: each sample's deviation, in % of its baseline, from the median of the
    previous `window` samples taken in the same rig state (one baseline per state, so a trip
    is never compared with drilling). None until half a window of baseline exists."""
    if states is not None and len(states) != len(values):
        raise ValueError("values and states differ in length")
    history: dict[str, deque[float]] = {}
    out: list[float | None] = []
    for i, v in enumerate(values):
        h = history.setdefault(states[i] if states is not None else "", deque(maxlen=window))
        dev = None
        if len(h) >= max(1, window // 2):
            base = median(h)
            dev = 100.0 * (v - base) / abs(base) if base else None
        out.append(dev)
        h.append(v)
    return out


def offset_deviation_pct(value: float, offset_values: Sequence[float]) -> float | None:
    """Torque & drag against offset wells' values at the same TVDSS / formation (their
    median), in %; None without offset values."""
    if not offset_values:
        return None
    base = median(offset_values)
    return 100.0 * (value - base) / abs(base) if base else None


def increasing_overpull_run(overpulls_kn: Sequence[float]) -> int:
    """Successive connections, ending at the latest, over which overpull kept increasing
    (1 = the last connection was no worse). A run of 3 or more is the stuck-pipe warning."""
    if not overpulls_kn:
        return 0
    run = 1
    for i in range(len(overpulls_kn) - 1, 0, -1):
        if overpulls_kn[i] <= overpulls_kn[i - 1]:
            break
        run += 1
    return run


@dataclass
class Crossing:
    index: int
    kind: str  # "raised" | "cleared"
    value: float


@dataclass
class ThresholdDetector:
    """Raise when the value is ≥ `on` for `min_consecutive` samples; clear only when it
    falls below `off` (< on): hysteresis stops an indicator chattering around the line."""

    on: float
    off: float
    min_consecutive: int = 2
    active: bool = False
    _run: int = 0
    crossings: list[Crossing] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.off > self.on:
            raise ValueError("off threshold must not exceed on threshold")

    def update(self, index: int, value: float) -> Crossing | None:
        if not self.active:
            self._run = self._run + 1 if value >= self.on else 0
            if self._run >= self.min_consecutive:
                self.active, self._run = True, 0
                c = Crossing(index, "raised", value)
                self.crossings.append(c)
                return c
        elif value < self.off:
            self.active = False
            c = Crossing(index, "cleared", value)
            self.crossings.append(c)
            return c
        return None


@dataclass(frozen=True)
class CementingRisk:
    level: str  # low | medium | high
    flags: list[str]


def cementing_risk(
    slurry_density_sg: float,
    offset_loss_mw_sg: list[float],
    offsets_with_cement_losses: int,
    offsets_cemented: int,
) -> CementingRisk:
    """Checklist before a cement job (master plan §Stage 7c): compare the planned slurry
    density with the mud weights at which offset wells lost circulation in the same
    formation, and with offsets that had losses while cementing the same section."""
    flags: list[str] = []
    score = 0
    if offset_loss_mw_sg:
        lowest = min(offset_loss_mw_sg)
        if slurry_density_sg >= lowest:
            flags.append(
                f"slurry {slurry_density_sg:.2f} SG ≥ lowest offset loss mud weight "
                f"{lowest:.2f} SG in this formation"
            )
            score += 2
        elif slurry_density_sg >= lowest - 0.05:
            flags.append(
                f"slurry within 0.05 SG of the lowest offset loss mud weight ({lowest:.2f} SG)"
            )
            score += 1
    if offsets_cemented and offsets_with_cement_losses:
        share = offsets_with_cement_losses / offsets_cemented
        flags.append(
            f"{offsets_with_cement_losses} of {offsets_cemented} offsets "
            "had losses while cementing here"
        )
        score += 2 if share >= 0.3 else 1
    level = "high" if score >= 3 else "medium" if score >= 1 else "low"
    return CementingRisk(level, flags)
