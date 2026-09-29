"""Source mnemonics → canonical channels (SI), with unit conversion (S12).

Every adapter (CSV replay, WITS0, later WITSML) turns a source record into a dict of
canonical channels through a `channel_mapping` table: (source, mnemonic) → (channel, unit).
The defaults below are seeded once; a rig with other mnemonics edits the table, not code.
"""

import csv
import io
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from app.core import units as u
from app.db.models.realtime import CHANNELS

# Factor (and offset) taking a value in `unit` to the canonical SI unit of its channel.
UNIT_FACTORS: dict[str, float] = {
    "m": 1.0,
    "ft": u.FT_TO_M,
    "kN": 1.0,
    "klbf": u.KLBF_TO_KN,
    "kN.m": 1.0,
    "kft.lbf": u.KFTLBF_TO_KNM,
    "kPa": 1.0,
    "psi": u.PSI_TO_KPA,
    "L/min": 1.0,
    "gpm": u.USGPM_TO_LPM,
    "m3": 1.0,
    "bbl": u.bbl_to_m3(1.0),
    "m/h": 1.0,
    "ft/h": u.FT_TO_M,
    "rpm": 1.0,
    "%": 1.0,
}


@dataclass(frozen=True)
class ChannelMap:
    mnemonic: str
    channel: str
    unit: str


# CSV replay files use the common LAS/WITSML-style mnemonics, in oilfield units.
CSV_DEFAULTS: tuple[ChannelMap, ...] = (
    ChannelMap("DBTM", "bit_depth_m", "ft"),
    ChannelMap("DMEA", "hole_depth_m", "ft"),
    ChannelMap("HKLA", "hookload_kn", "klbf"),
    ChannelMap("WOBA", "wob_kn", "klbf"),
    ChannelMap("RPMA", "rpm", "rpm"),
    ChannelMap("TQA", "torque_knm", "kft.lbf"),
    ChannelMap("SPPA", "spp_kpa", "psi"),
    ChannelMap("MFIA", "flow_in_lpm", "gpm"),
    ChannelMap("MFOA", "flow_out_lpm", "gpm"),
    ChannelMap("TVA", "pit_volume_m3", "bbl"),
    ChannelMap("ROPA", "rop_m_h", "ft/h"),
    ChannelMap("GASA", "gas_pct", "%"),
)
# WITS0 record 1 (general time-based) item codes. Rigs configure WITS differently: check
# these against the rig's WITS set-up before trusting a live feed (the table is editable).
WITS0_DEFAULTS: tuple[ChannelMap, ...] = (
    ChannelMap("0108", "bit_depth_m", "m"),
    ChannelMap("0110", "hole_depth_m", "m"),
    ChannelMap("0113", "rop_m_h", "m/h"),
    ChannelMap("0114", "hookload_kn", "kN"),
    ChannelMap("0116", "wob_kn", "kN"),
    ChannelMap("0118", "torque_knm", "kN.m"),
    ChannelMap("0120", "rpm", "rpm"),
    ChannelMap("0121", "spp_kpa", "kPa"),
    ChannelMap("0127", "pit_volume_m3", "m3"),
    ChannelMap("0130", "flow_out_lpm", "L/min"),
    ChannelMap("0131", "flow_in_lpm", "L/min"),
    ChannelMap("0141", "gas_pct", "%"),
)
DEFAULTS: dict[str, tuple[ChannelMap, ...]] = {"csv": CSV_DEFAULTS, "wits0": WITS0_DEFAULTS}
TIME_COLUMN = "TIME"


def to_canonical(
    record: Mapping[str, str | float | None], mapping: Iterable[ChannelMap]
) -> tuple[dict[str, float | None], dict[str, str]]:
    """Canonical channel values of one source record, and a quality flag per channel that is
    missing or unreadable (the sample is kept; a gap is not a zero)."""
    out: dict[str, float | None] = dict.fromkeys(CHANNELS)
    quality: dict[str, str] = {}
    for m in mapping:
        if m.channel not in out:
            continue
        raw = record.get(m.mnemonic)
        if raw is None or raw == "":
            quality[m.channel] = "missing"
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            quality[m.channel] = "unreadable"
            continue
        if not math.isfinite(v) or v <= -999.0:  # -999.25 is the LAS null
            quality[m.channel] = "missing"
            continue
        out[m.channel] = v * UNIT_FACTORS[m.unit]
    for ch in CHANNELS:
        if out[ch] is None and ch not in quality:
            quality[ch] = "unmapped"
    return out, quality


def write_csv(
    t0: datetime, dt_s: float, data: Mapping[str, np.ndarray], mapping: Iterable[ChannelMap]
) -> str:
    """A replay file from canonical arrays, in the mapping's units (the inverse of
    `to_canonical`), one row per sample with an ISO-8601 UTC TIME column."""
    maps = list(mapping)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow([TIME_COLUMN, *(m.mnemonic for m in maps)])
    n = len(next(iter(data.values())))
    for i in range(n):
        t = (t0 + timedelta(seconds=dt_s * i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        w.writerow([t, *(f"{float(data[m.channel][i]) / UNIT_FACTORS[m.unit]:.4f}" for m in maps)])
    return buf.getvalue()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
