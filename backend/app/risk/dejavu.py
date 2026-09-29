"""S7d "Déjà Vu": does the last 30 minutes look like the run-up to a past incident?

Library: for every historical event with real-time data, the 90 minutes before it
(`pattern_signature`). Query: the live well's last 30 minutes. Two stages (master plan
§Stage 7d), implemented here in NumPy rather than with stumpy/tslearn (ADR-B17):

A. **MASS** per channel: the z-normalised Euclidean distance of the query at every offset
   inside each 90-minute signature (sliding dot products by FFT), summed over channels. The
   best offset also says how long before that past event the match ends.
B. For the 20 best candidates, **banded DTW** (Sakoe-Chiba 10%) on the aligned segment, each
   channel as its change from the segment's first 5 minutes in units of the channel's
   typical range (the plan's level term folded into the shape: z-normalised shape alone
   would treat a small wiggle and a big swing alike). The summed DTW distance is divided by
   how much both segments change, so identical changes score 0 and unrelated or quiet
   windows score about 1: two quiet windows are not "the same incident".

similarity = exp(-D / tau), with tau calibrated on precursor-free windows so that a
similarity of 0.8 is reached by about 1% of them. It is a similarity, never a probability.

Channels are compared in their operating state only: mechanical channels over drilling
samples, hydraulic ones over pumping samples, the gaps forward-filled, so a connection's
pumps-off dip does not dominate the shape.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np

QUERY_STEPS = 180  # 30 min at 10 s
SIGNATURE_STEPS = 540  # 90 min
DOWNSAMPLE = 3  # stage B at 30 s
BAND = 0.10
TOP_A = 20
ALERT_SIMILARITY = 0.8
# A match must end in the last 40 min before the past event: the start of each signature is
# ordinary drilling, and a live window matching *that* says nothing.
MATCH_END_WITHIN = 240
MIN_OFFSET = SIGNATURE_STEPS - QUERY_STEPS - MATCH_END_WITHIN
CHANNELS = ("torque", "hookload", "spp", "rop", "imbalance", "pit", "gas")
# Typical ranges for the level term (canonical units) and z-normalisation floors.
SCALE = {
    "torque": 4.0,
    "hookload": 40.0,
    "spp": 1500.0,
    "rop": 8.0,
    "imbalance": 8.0,
    "pit": 3.0,
    "gas": 1.0,
}
NOISE = {k: v / 20 for k, v in SCALE.items()}


def _ffill(x: np.ndarray, keep: np.ndarray) -> np.ndarray:
    idx = np.where(keep, np.arange(len(x)), 0)
    np.maximum.accumulate(idx, out=idx)
    out = x[idx].astype(float)
    if not keep.any():
        return np.zeros_like(out)
    first = int(np.argmax(keep))
    out[:first] = x[first]
    return out


def prepare(d: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """The matching channels of a raw window, each in its operating state."""
    drilling = d["wob_kn"] > 10
    pumping = d["flow_in_lpm"] > 200
    fi = np.where(pumping, d["flow_in_lpm"], 1.0)
    imb = np.where(pumping, (d["flow_out_lpm"] - d["flow_in_lpm"]) / fi * 100, 0.0)
    pit = d["pit_volume_m3"] - d["pit_volume_m3"][0]
    return {
        "torque": _ffill(d["torque_knm"], drilling),
        "hookload": _ffill(d["hookload_kn"], drilling),
        "spp": _ffill(d["spp_kpa"], pumping),
        "rop": _ffill(d["rop_m_h"], drilling),
        "imbalance": _ffill(imb, pumping),
        "pit": pit.astype(float),
        "gas": d["gas_pct"].astype(float),
    }


def mass(query: np.ndarray, series: np.ndarray, noise: float) -> np.ndarray:
    """z-normalised Euclidean distance of `query` at every offset of `series` (MASS)."""
    m, n = len(query), len(series)
    if n < m:
        raise ValueError("series shorter than query")
    q = query - query.mean()
    sq = max(float(q.std()), noise)
    size = 1 << (n + m - 1).bit_length()
    qt = np.fft.irfft(np.fft.rfft(series, size) * np.fft.rfft(q[::-1], size), size)[m - 1 : n]
    c1 = np.concatenate(([0.0], np.cumsum(series)))
    c2 = np.concatenate(([0.0], np.cumsum(series * series)))
    mu = (c1[m:] - c1[:-m]) / m
    sd = np.sqrt(np.maximum((c2[m:] - c2[:-m]) / m - mu * mu, 0.0))
    sd = np.maximum(sd, noise)
    # q has zero mean, so the window mean cancels out of the dot product.
    corr = qt / (m * sq * sd)
    out: np.ndarray = np.sqrt(np.maximum(2 * m * (1 - np.clip(corr, -1, 1)), 0.0))
    return out


def dtw(a: np.ndarray, b: np.ndarray, band: int) -> float:
    """Banded (Sakoe-Chiba) DTW distance between two equal-length series."""
    n = len(a)
    inf = np.inf
    prev = np.full(n + 1, inf)
    prev[0] = 0.0
    for i in range(1, n + 1):
        cur = np.full(n + 1, inf)
        lo, hi = max(1, i - band), min(n, i + band)
        cost = np.abs(a[i - 1] - b[lo - 1 : hi])
        for k, j in enumerate(range(lo, hi + 1)):
            cur[j] = cost[k] + min(prev[j], prev[j - 1], cur[j - 1])
        prev = cur
    return float(prev[n])


BASELINE_POINTS = 10  # the first 5 min of a downsampled 30-min segment


QUIET = 0.35  # combined change (in typical ranges) below which windows are "both quiet"
SMOOTH = 6  # 1-min moving average before comparing


def _segment(x: np.ndarray, channel: str) -> np.ndarray:
    """A 30-min segment as its change from its own first 5 minutes, smoothed over 1 min and
    averaged to 30 s, in units of the channel's typical range: quiet channels contribute
    ~0, a precursor must be matched in size and sign, and a well's absolute level (its own
    torque, its own tank) drops out."""
    padded = np.pad(x, (SMOOTH // 2, SMOOTH - 1 - SMOOTH // 2), mode="edge")
    sm = np.convolve(padded, np.ones(SMOOTH) / SMOOTH, mode="valid")  # no zero-padded ends
    n = len(sm) // DOWNSAMPLE * DOWNSAMPLE
    blocks = sm[:n].reshape(-1, DOWNSAMPLE).mean(axis=1)
    out: np.ndarray = (blocks - blocks[:BASELINE_POINTS].mean()) / SCALE[channel]
    return out


@dataclass
class Signature:
    id: int
    event_type: str
    channels: dict[str, np.ndarray]
    drilling_share: float
    hole_size_in: float | None
    well_id: int | None = None
    event_id: int | None = None
    meta: dict[str, Any] | None = None


@dataclass
class Match:
    signature: Signature
    distance: float
    similarity: float
    offset: int  # query aligned to signature[offset : offset + QUERY_STEPS]

    @property
    def minutes_before_event(self) -> float:
        """How long before the past event the matched segment ends."""
        return (SIGNATURE_STEPS - (self.offset + QUERY_STEPS)) * 10 / 60


def _hole_class(h: float | None) -> str | None:
    return None if h is None else ("large" if h > 10 else "small")


def search(
    query: dict[str, np.ndarray],
    library: list[Signature],
    tau: float,
    drilling_share: float,
    hole_size_in: float | None = None,
    exclude_well: int | None = None,
    top: int = 3,
) -> list[Match]:
    """Best matches for a prepared 30-min query, most similar first."""
    cands: list[tuple[float, int, Signature]] = []
    for sig in library:
        if exclude_well is not None and sig.well_id == exclude_well:
            continue
        if abs(sig.drilling_share - drilling_share) > 0.3:
            continue  # context gate: compare drilling with drilling
        hq, hs = _hole_class(hole_size_in), _hole_class(sig.hole_size_in)
        if hq and hs and hq != hs:
            continue
        total = np.zeros(SIGNATURE_STEPS - QUERY_STEPS + 1)
        for ch in CHANNELS:
            dp = mass(query[ch], sig.channels[ch], NOISE[ch])
            total += dp * dp / QUERY_STEPS
        k = MIN_OFFSET + int(np.argmin(total[MIN_OFFSET:]))
        cands.append((float(total[k]), k, sig))
    cands.sort(key=lambda c: c[0])
    band = max(1, int(QUERY_STEPS // DOWNSAMPLE * BAND))
    out: list[Match] = []
    for _, off, sig in cands[:TOP_A]:
        num = den = 0.0
        for ch in CHANNELS:
            q = _segment(query[ch], ch)
            seg = _segment(sig.channels[ch][off : off + QUERY_STEPS], ch)
            num += dtw(q, seg, band) / len(q)
            den += float(np.mean(np.abs(q)) + np.mean(np.abs(seg)))
        # 0 = the same change in the same channels; about 1 = unrelated (or both quiet).
        dist = num / max(den, QUIET)
        out.append(Match(sig, dist, float(np.exp(-dist / tau)), off))
    out.sort(key=lambda m: m.distance)
    return out[:top]


def calibrate_tau(normal_best_distances: list[float], false_match_rate: float = 0.01) -> float:
    """tau so that `false_match_rate` of precursor-free windows reach ALERT_SIMILARITY."""
    d = float(np.quantile(np.asarray(normal_best_distances), false_match_rate))
    return float(d / -np.log(ALERT_SIMILARITY))
