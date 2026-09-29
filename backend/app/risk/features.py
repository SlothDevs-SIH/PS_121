"""Rolling real-time features (S7b) on the 10 s grid, computed the same way for training and
for live scoring.

At sample i each feature compares the last few minutes with a *baseline*: the hour that
ended 15 minutes earlier (samples i-360 .. i-90), taken in the same rig state (drilling
samples for the mechanical channels, pumping samples for the hydraulic ones). That is the
"deviation from a rolling state-conditioned baseline" of master plan §Stage 7c, so a
classifier learns changes, not a well's absolute levels.
"""

from dataclasses import dataclass

import numpy as np

from app.physics.indicators import KN_TO_LBF, KNM_TO_FTLBF

W2, W5, W15 = 12, 30, 90
BASE_FROM, BASE_TO = 360, 90  # baseline window: from i-360 to i-90
MIN_HISTORY = BASE_FROM  # features need an hour of history

FEATURES: tuple[str, ...] = (
    "imb_2",
    "imb_5",
    "imb_15",
    "imb_shift",
    "pit_d5",
    "pit_d15",
    "torque_rel",
    "torque_std_rel",
    "hook_std_rel",
    "overpull_15",
    "rop_rel",
    "wob_rel",
    "spp_rel",
    "gas_rel",
    "mse_rel",
    "drilling_share_15",
)

LABELS = {
    "imb_2": "flow out vs in, last 2 min",
    "imb_5": "flow out vs in, last 5 min",
    "imb_15": "flow out vs in, last 15 min",
    "imb_shift": "change in return flow vs the last hour",
    "pit_d5": "pit volume change, 5 min",
    "pit_d15": "pit volume change, 15 min",
    "torque_rel": "torque vs baseline",
    "torque_std_rel": "torque oscillation vs baseline",
    "hook_std_rel": "hookload scatter vs baseline",
    "overpull_15": "overpull, last 15 min",
    "rop_rel": "ROP vs baseline",
    "wob_rel": "WOB vs baseline",
    "spp_rel": "standpipe pressure vs baseline",
    "gas_rel": "gas vs baseline",
    "mse_rel": "mechanical specific energy vs baseline",
    "drilling_share_15": "share of drilling time, 15 min",
}


def _csum(x: np.ndarray) -> np.ndarray:
    return np.concatenate(([0.0], np.cumsum(x)))


@dataclass
class _Masked:
    """Windowed mean/std of a channel over the samples where a mask is true."""

    s1: np.ndarray
    s2: np.ndarray
    n: np.ndarray

    @classmethod
    def of(cls, x: np.ndarray, mask: np.ndarray) -> "_Masked":
        m = mask.astype(float)
        return cls(_csum(x * m), _csum(x * x * m), _csum(m))

    def mean(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        n = self.n[b] - self.n[a]
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(n > 0, (self.s1[b] - self.s1[a]) / n, np.nan)

    def std(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        n = self.n[b] - self.n[a]
        with np.errstate(invalid="ignore", divide="ignore"):
            mu = (self.s1[b] - self.s1[a]) / n
            var = (self.s2[b] - self.s2[a]) / n - mu * mu
            return np.where(n > 1, np.sqrt(np.maximum(var, 0.0)), np.nan)


def _rel(now: np.ndarray, base: np.ndarray, floor: float) -> np.ndarray:
    out: np.ndarray = (now - base) / np.maximum(np.abs(base), floor)
    return out


def mse_series(d: dict[str, np.ndarray], bit_in: float = 8.5) -> np.ndarray:
    """Teale MSE (psi-scaled units are enough for a ratio feature), 0 when not drilling."""
    area = np.pi * bit_in**2 / 4
    rop_ft_h = np.maximum(d["rop_m_h"] / 0.3048, 0.5)
    mse = d["wob_kn"] * KN_TO_LBF / area + (
        120 * np.pi * d["rpm"] * d["torque_knm"] * KNM_TO_FTLBF / (area * rop_ft_h)
    )
    out: np.ndarray = np.where(d["wob_kn"] > 0, mse, 0.0)
    return out


def compute(d: dict[str, np.ndarray], at: np.ndarray, bit_in: float = 8.5) -> np.ndarray:
    """Feature matrix (len(at) x len(FEATURES)) at sample indices `at` (each ≥ MIN_HISTORY)."""
    at = np.asarray(at, dtype=int)
    if len(at) and at.min() < MIN_HISTORY:
        raise ValueError("features need MIN_HISTORY samples before each index")
    end = at + 1
    drilling = d["wob_kn"] > 10
    pumping = d["flow_in_lpm"] > 200
    fi = np.where(pumping, d["flow_in_lpm"], 1.0)
    imb = np.where(pumping, (d["flow_out_lpm"] - d["flow_in_lpm"]) / fi * 100, 0.0)
    m_imb = _Masked.of(imb, pumping)
    m_tq = _Masked.of(d["torque_knm"], drilling)
    m_hk = _Masked.of(d["hookload_kn"], drilling)
    m_rop = _Masked.of(d["rop_m_h"], drilling)
    m_wob = _Masked.of(d["wob_kn"], drilling)
    m_spp = _Masked.of(d["spp_kpa"], pumping)
    m_gas = _Masked.of(d["gas_pct"], np.ones_like(pumping))
    m_mse = _Masked.of(mse_series(d, bit_in), drilling)
    m_dr = _Masked.of(drilling.astype(float), np.ones_like(pumping))
    b0, b1 = end - BASE_FROM, end - BASE_TO

    def win(w: int) -> tuple[np.ndarray, np.ndarray]:
        return end - w, end

    base_hook_wt = m_hk.mean(b0, b1) + m_wob.mean(b0, b1)  # string weight while drilling
    hook = d["hookload_kn"]
    overpull = np.array([np.max(hook[e - W15 : e]) for e in end]) - base_hook_wt
    pit = d["pit_volume_m3"]

    cols = {
        "imb_2": m_imb.mean(*win(W2)),
        "imb_5": m_imb.mean(*win(W5)),
        "imb_15": m_imb.mean(*win(W15)),
        "imb_shift": m_imb.mean(*win(W5)) - m_imb.mean(b0, b1),
        "pit_d5": pit[end - 1] - pit[end - W5],
        "pit_d15": pit[end - 1] - pit[end - W15],
        "torque_rel": _rel(m_tq.mean(*win(W5)), m_tq.mean(b0, b1), 1.0),
        "torque_std_rel": _rel(m_tq.std(*win(W5)), m_tq.std(b0, b1), 0.3),
        "hook_std_rel": _rel(m_hk.std(*win(W5)), m_hk.std(b0, b1), 3.0),
        "overpull_15": overpull,
        "rop_rel": _rel(m_rop.mean(*win(W5)), m_rop.mean(b0, b1), 1.0),
        "wob_rel": _rel(m_wob.mean(*win(W5)), m_wob.mean(b0, b1), 5.0),
        "spp_rel": _rel(m_spp.mean(*win(W5)), m_spp.mean(b0, b1), 100.0),
        "gas_rel": _rel(m_gas.mean(*win(W5)), m_gas.mean(b0, b1), 0.1),
        "mse_rel": _rel(m_mse.mean(*win(W5)), m_mse.mean(b0, b1), 1000.0),
        "drilling_share_15": m_dr.mean(*win(W15)),
    }
    return np.column_stack([cols[f] for f in FEATURES]).astype(float)
