"""Minimum-curvature wellbore trajectory calculation (master plan §Stage 4).

Given survey stations (MD, inclination, azimuth), returns north/east offsets from the
surface location, TVD below the depth reference, and dogleg severity. Angles are degrees,
lengths metres. Azimuth is measured clockwise from north (grid north once corrected).

    beta = arccos(cos(I2-I1) - sin I1 sin I2 (1 - cos(A2-A1)))
    RF   = (2/beta) tan(beta/2)            (RF -> 1 as beta -> 0)
    dN   = dMD/2 (sin I1 cos A1 + sin I2 cos A2) RF
    dE   = dMD/2 (sin I1 sin A1 + sin I2 sin A2) RF
    dTVD = dMD/2 (cos I1 + cos I2) RF
    DLS  = beta[deg] * 30 / dMD            (deg/30 m)

Minimum curvature is exact for circular arcs, which the tests exploit.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class Trajectory:
    md: FloatArray
    inc: FloatArray
    azi: FloatArray
    north: FloatArray
    east: FloatArray
    tvd: FloatArray
    dls: FloatArray  # deg/30 m, 0 at the first station

    def position_at_md(self, md: float) -> tuple[float, float, float]:
        """(north, east, tvd) at an arbitrary MD, linear between stations (clamped to range).

        Linear interpolation between stations spaced <= 30 m is within centimetres of the
        exact arc for the dogleg severities seen in practice; stations are the exact values.
        """
        return (
            float(np.interp(md, self.md, self.north)),
            float(np.interp(md, self.md, self.east)),
            float(np.interp(md, self.md, self.tvd)),
        )

    def md_at_tvd(self, tvd: float) -> float | None:
        """First MD where the wellbore reaches `tvd`, or None if it never does.

        Assumes TVD is non-decreasing along the hole (true for non-horizontal wells).
        """
        if tvd < self.tvd[0] or tvd > self.tvd[-1]:
            return None
        idx = int(np.searchsorted(self.tvd, tvd, side="left"))
        if idx == 0:
            return float(self.md[0])
        t0, t1 = self.tvd[idx - 1], self.tvd[idx]
        m0, m1 = self.md[idx - 1], self.md[idx]
        if t1 == t0:
            return float(m0)
        return float(m0 + (tvd - t0) * (m1 - m0) / (t1 - t0))


def minimum_curvature(
    md: FloatArray | list[float],
    inc_deg: FloatArray | list[float],
    azi_deg: FloatArray | list[float],
) -> Trajectory:
    md_a = np.asarray(md, dtype=np.float64)
    inc_a = np.asarray(inc_deg, dtype=np.float64)
    azi_a = np.asarray(azi_deg, dtype=np.float64)
    if not (md_a.shape == inc_a.shape == azi_a.shape) or md_a.ndim != 1 or md_a.size < 1:
        raise ValueError("md, inc and azi must be 1-D arrays of equal, non-zero length")
    if np.any(np.diff(md_a) <= 0):
        raise ValueError("measured depths must be strictly increasing")
    if np.any((inc_a < 0) | (inc_a > 180)):
        raise ValueError("inclination must be within [0, 180] degrees")

    i = np.radians(inc_a)
    a = np.radians(azi_a)
    i1, i2, a1, a2 = i[:-1], i[1:], a[:-1], a[1:]
    dmd = np.diff(md_a)

    cos_beta = np.cos(i2 - i1) - np.sin(i1) * np.sin(i2) * (1.0 - np.cos(a2 - a1))
    beta = np.arccos(np.clip(cos_beta, -1.0, 1.0))
    small = beta < 1e-7
    safe_beta = np.where(small, 1.0, beta)
    rf = np.where(small, 1.0 + beta**2 / 12.0, (2.0 / safe_beta) * np.tan(safe_beta / 2.0))

    dn = dmd / 2.0 * (np.sin(i1) * np.cos(a1) + np.sin(i2) * np.cos(a2)) * rf
    de = dmd / 2.0 * (np.sin(i1) * np.sin(a1) + np.sin(i2) * np.sin(a2)) * rf
    dtvd = dmd / 2.0 * (np.cos(i1) + np.cos(i2)) * rf

    north = np.concatenate([[0.0], np.cumsum(dn)])
    east = np.concatenate([[0.0], np.cumsum(de)])
    tvd = np.concatenate([[md_a[0] * np.cos(i[0])], md_a[0] * np.cos(i[0]) + np.cumsum(dtvd)])
    dls = np.concatenate([[0.0], np.degrees(beta) * 30.0 / dmd])
    return Trajectory(md=md_a, inc=inc_a, azi=azi_a, north=north, east=east, tvd=tvd, dls=dls)


def vertical_stations(
    td_m: float, step_m: float = 30.0
) -> tuple[FloatArray, FloatArray, FloatArray]:
    md = np.arange(0.0, td_m + 1e-9, step_m)
    if md[-1] < td_m:
        md = np.append(md, td_m)
    zeros = np.zeros_like(md)
    return md, zeros, zeros.copy()


def directional_stations(
    td_m: float,
    kop_m: float,
    build_rate_deg_30m: float,
    max_inc_deg: float,
    azimuth_deg: float,
    drop_start_m: float | None = None,
    drop_rate_deg_30m: float = 0.0,
    final_inc_deg: float = 0.0,
    step_m: float = 30.0,
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Survey stations for a J profile (vertical → build → hold) or S profile (… → drop)."""
    md = np.arange(0.0, td_m + 1e-9, step_m)
    if md[-1] < td_m:
        md = np.append(md, td_m)
    inc = np.clip((md - kop_m) * build_rate_deg_30m / 30.0, 0.0, max_inc_deg)
    if drop_start_m is not None and drop_rate_deg_30m > 0:
        dropped = max_inc_deg - (md - drop_start_m) * drop_rate_deg_30m / 30.0
        inc = np.where(md > drop_start_m, np.maximum(dropped, final_inc_deg), inc)
    azi = np.full_like(md, azimuth_deg % 360.0)
    return md, inc, azi
