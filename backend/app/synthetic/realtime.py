"""Synthetic real-time drilling channels (10 s steps) with planted precursors.

EVERYTHING HERE IS ILLUSTRATIVE (master plan §12.3). The simulator drills stands with
connections between them and adds, before each event, the precursor pattern the master
plan's Stage 7b/7c/7d literature describes for that problem type. Models trained or
evaluated on it measure how well they recover *planted* patterns; that says nothing about
Assam wells and must be quoted as such.

Channels are canonical SI (app.core.units): depths m, hookload/WOB kN, torque kN.m, SPP kPa,
flows L/min, pit volume m³, ROP m/h, gas %.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

DT_S = 10
CHANNELS = (
    "bit_depth_m",
    "hole_depth_m",
    "hookload_kn",
    "wob_kn",
    "rpm",
    "torque_knm",
    "spp_kpa",
    "flow_in_lpm",
    "flow_out_lpm",
    "pit_volume_m3",
    "rop_m_h",
    "gas_pct",
)
STAND_M = 28.5
# Problems that show in the drilling channels (cementing problems don't, while drilling).
REALTIME_TYPES = ("LOSS", "KICK", "STUCK", "TIGHT", "TORQUE", "BALLING", "INSTAB", "OVERP")


@dataclass(frozen=True)
class Planted:
    """An event planted in a simulated window: its type starts at step `start`, and its
    precursor ramps up over the `lead_steps` before that."""

    event_type: str
    start: int
    lead_steps: int
    severity: float  # 0.5-1.5 scales the precursor and the event
    end: int | None = None  # the problem is over (cured, freed) from this step; None = never


@dataclass
class Episode:
    well: str
    t0: datetime
    data: dict[str, np.ndarray]
    planted: list[Planted] = field(default_factory=list)
    formation: str | None = None
    hole_size_in: float = 8.5
    source_event_id: str | None = None  # the generator's event id, for signatures

    @property
    def n(self) -> int:
        return len(self.data["bit_depth_m"])

    def times(self) -> list[datetime]:
        return [self.t0 + timedelta(seconds=DT_S * i) for i in range(self.n)]


@dataclass
class _Base:
    rop_m_h: float
    wob_kn: float
    rpm: float
    flow_lpm: float
    mw_sg: float
    hole_in: float


def _ramp(i: int, p: Planted) -> float:
    """0 before the precursor, rising to 1 at the event start, 1 until it ends."""
    if p.end is not None and i >= p.end:
        return 0.0
    if i >= p.start:
        return 1.0
    k = i - (p.start - p.lead_steps)
    return 0.0 if k < 0 else (k / p.lead_steps) ** 1.6


def simulate(
    rng: np.random.Generator,
    start_depth_m: float,
    n_steps: int,
    base: _Base,
    planted: Sequence[Planted] = (),
) -> dict[str, np.ndarray]:
    """Drill from `start_depth_m` for `n_steps` x 10 s: stands with connections, noise,
    and each planted precursor/event superimposed on the physics of the operation."""
    out = {c: np.zeros(n_steps) for c in CHANNELS}
    hole = start_depth_m
    bit = start_depth_m
    pit = float(rng.uniform(55, 75))
    gas_bg = float(rng.uniform(0.2, 0.6))
    next_connection = hole + STAND_M - (hole % STAND_M)
    conn_left = 0  # steps remaining in the current connection
    conn_len = 54  # 9 min: 2 off bottom circulating, 5 in slips, 2 back to bottom
    stuck = False
    torque_spike = 0.0
    for i in range(n_steps):
        amp = {p.event_type: _ramp(i, p) * p.severity for p in planted}
        active = {p.event_type for p in planted if p.start <= i < (p.end or n_steps)}
        stuck = "STUCK" in active

        string_wt = 0.30 * bit * (1 - base.mw_sg / 7.85) + 180.0  # buoyed pipe + block, kN
        rop = base.rop_m_h * float(np.exp(rng.normal(0, 0.12)))
        rop *= 1 + 0.9 * amp.get("KICK", 0) + 0.6 * amp.get("OVERP", 0)
        rop *= 1 - 0.65 * min(1.0, amp.get("BALLING", 0))
        wob = base.wob_kn * (1 + 0.25 * amp.get("BALLING", 0)) + rng.normal(0, 4)
        rpm = base.rpm + rng.normal(0, 3)
        flow_in = base.flow_lpm + rng.normal(0, 15)

        if conn_left == 0 and hole >= next_connection and not stuck:
            conn_left = conn_len
            next_connection += STAND_M
        if stuck:
            # Stuck: no progress, rotation stalls, the driller works the pipe.
            phase = "stuck"
            conn_left = 0
        elif conn_left > 0:
            k = conn_len - conn_left
            phase = "off_bottom" if k < 12 or k >= 42 else "slips"
            conn_left -= 1
        else:
            phase = "drilling"

        if phase == "drilling":
            hole += rop * DT_S / 3600
            bit = hole
            hook = string_wt - wob
            torque = 2.0 + 0.045 * wob + 0.0006 * bit
            torque *= 1 - 0.2 * amp.get("BALLING", 0)
            flow = flow_in
        elif phase == "off_bottom":
            k = conn_len - conn_left - 1
            bit = hole - (min(k, 11) if k < 12 else max(0, 53 - k)) * 0.25
            drag = 25 + 150 * amp.get("TIGHT", 0) + 170 * amp.get("STUCK", 0)
            drag += 60 * amp.get("INSTAB", 0)
            hook = string_wt + drag * float(rng.uniform(0.6, 1.0)) * (k < 12)
            wob, rop = 0.0, 0.0
            torque = 1.2 + 0.0004 * bit
            flow = flow_in
        elif phase == "slips":
            bit = hole - 3.0
            hook = 180.0 + rng.normal(0, 3)
            wob, rop, rpm = 0.0, 0.0, 0.0
            torque = 0.0
            flow_in = 0.0
            flow = 0.0
        else:  # stuck
            hook = string_wt + 250 + 180 * float(np.sin(i / 3.0)) ** 2  # jarring / overpull
            wob, rop = 0.0, 0.0
            rpm = max(0.0, rpm * 0.1)
            torque = 18 + rng.normal(0, 2)
            flow = flow_in * 0.95

        # Mechanical precursors on the torque.
        torque *= 1 + 0.35 * amp.get("STUCK", 0) + 0.15 * amp.get("TIGHT", 0)
        spike_p = 0.02 + 0.25 * amp.get("TORQUE", 0) + 0.15 * amp.get("INSTAB", 0)
        if rpm > 5 and rng.random() < spike_p:
            torque_spike = float(rng.uniform(3, 9)) * (1 + amp.get("TORQUE", 0))
        torque += torque_spike + rng.normal(0, 0.25 * (1 + 2 * amp.get("INSTAB", 0)))
        torque_spike *= 0.5
        # Stick-slip: a torque oscillation that grows as the string starts to bind.
        mech = amp.get("STUCK", 0) + 0.6 * amp.get("TIGHT", 0)
        if phase == "drilling" and mech > 0:
            torque += 2.2 * mech * float(np.sin(i * 0.9 + rng.uniform(0, 0.6)))
            hook += rng.normal(0, 12 * mech)  # erratic weight transfer

        # Returns and pit: losses take mud, a kick gives it back.
        loss_frac = 0.22 * amp.get("LOSS", 0) ** 2
        if "LOSS" in active:
            loss_frac = 0.35 + 0.35 * min(1.0, amp.get("LOSS", 0))
        gain_frac = 0.12 * amp.get("KICK", 0) + (0.25 if "KICK" in active else 0)
        flow_out = flow * (1 - loss_frac + gain_frac) + rng.normal(0, 18) if flow > 0 else 0.0
        flow_out = max(0.0, flow_out)
        pit += (flow_out - flow) * DT_S / 60 / 1000  # L/min → m³ per step
        pit -= 0.00015 * rop  # new hole takes mud
        if phase == "slips" and "KICK" in active:
            pit += 0.08  # the well flows with the pumps off
        spp = 0.0
        if flow_in > 0:
            spp = 3.2e-3 * flow_in**2 * (base.mw_sg / 1.2) * (1 + bit / 9000)
            spp *= 1 - 0.04 * amp.get("LOSS", 0) - 0.06 * amp.get("KICK", 0)
            spp *= 1 + 0.06 * amp.get("BALLING", 0) + 0.10 * amp.get("INSTAB", 0) * rng.random()
            spp += rng.normal(0, 40)
        gas = gas_bg * (1 + 6 * amp.get("KICK", 0) + 4 * amp.get("OVERP", 0))
        if phase == "off_bottom":
            gas *= 1 + 1.5 * amp.get("OVERP", 0)  # connection gas
        gas = max(0.0, gas + rng.normal(0, 0.05))

        out["bit_depth_m"][i] = bit
        out["hole_depth_m"][i] = hole
        out["hookload_kn"][i] = max(0.0, hook + rng.normal(0, 4))
        out["wob_kn"][i] = max(0.0, wob)
        out["rpm"][i] = max(0.0, rpm)
        out["torque_knm"][i] = max(0.0, torque)
        out["spp_kpa"][i] = max(0.0, spp)
        out["flow_in_lpm"][i] = max(0.0, flow_in)
        out["flow_out_lpm"][i] = flow_out
        out["pit_volume_m3"][i] = pit + rng.normal(0, 0.02)
        out["rop_m_h"][i] = max(0.0, rop)
        out["gas_pct"][i] = gas
    return out


def base_for(rng: np.random.Generator, hole_in: float, mw_sg: float) -> _Base:
    big = hole_in > 10
    return _Base(
        rop_m_h=float(rng.uniform(14, 26) if big else rng.uniform(8, 16)),
        wob_kn=float(rng.uniform(90, 140) if big else rng.uniform(70, 110)),
        rpm=float(rng.uniform(110, 150)),
        flow_lpm=float(rng.uniform(3000, 3600) if big else rng.uniform(1900, 2400)),
        mw_sg=mw_sg,
        hole_in=hole_in,
    )


PRE_STEPS = 720  # 2 h of drilling before the event
POST_STEPS = 120  # 20 min of the event


def event_episode(
    rng: np.random.Generator,
    well: str,
    event_id: str,
    event_type: str,
    md_m: float,
    start: datetime,
    formation: str,
    hole_in: float,
    mw_sg: float,
) -> Episode:
    """2 h 20 min around one event: normal drilling, the precursor over its last 30-60 min,
    then the event itself. The event reaches `md_m` at step PRE_STEPS."""
    base = base_for(rng, hole_in, mw_sg)
    lead = int(rng.uniform(180, 360))  # 30-60 min
    sev = float(rng.uniform(0.6, 1.4))
    planted = [Planted(event_type, PRE_STEPS, lead, sev)]
    # Start deep enough above the event that the bit reaches it about when the event begins.
    depth0 = max(50.0, md_m - base.rop_m_h * PRE_STEPS * DT_S / 3600 * 0.72)
    data = simulate(rng, depth0, PRE_STEPS + POST_STEPS, base, planted)
    t0 = start - timedelta(seconds=DT_S * PRE_STEPS)
    return Episode(well, t0, data, planted, formation, hole_in, event_id)


def normal_episode(
    rng: np.random.Generator,
    well: str,
    depth_m: float,
    start: datetime,
    hole_in: float,
    mw_sg: float,
) -> Episode:
    base = base_for(rng, hole_in, mw_sg)
    data = simulate(rng, depth_m, PRE_STEPS + POST_STEPS, base)
    return Episode(well, start, data, [], None, hole_in, None)


REPLAY_ROP_M_H = (12.0, 30.0)  # sized so the next formation is about 3.5 h of drilling away
REPLAY_REACH_H = 3.5
REPLAY_FALLBACK_LOSS = 1440  # 4 h: where losses go when the next formation is out of reach


def replay_episode(
    seed: int,
    well: str,
    start_md_m: float,
    t0: datetime,
    next_top_md_m: float,
    hole_in: float,
    mw_sg: float,
) -> Episode:
    """The drilling well's next hours, for the replay demo: drilling on from `start_md_m`, bit
    balling after about 1.5 h (cleared 15 min later), then losses 4 m into the next formation
    (or, when even a fast bit would not reach it in 12 h, after 4 h where the bit is).

    Two passes with the same seed: the first finds when the bit reaches the formation (a loss
    precursor does not change ROP or the random draws, so the second pass follows the same
    path up to the planted loss)."""
    base = base_for(np.random.default_rng([seed, 0]), hole_in, mw_sg)
    lo, hi = REPLAY_ROP_M_H
    base.rop_m_h = float(np.clip((next_top_md_m - start_md_m) / REPLAY_REACH_H, lo, hi))
    balling = Planted("BALLING", 540, 240, 1.0, end=630)
    probe = simulate(np.random.default_rng([seed, 1]), start_md_m, 4320, base, [balling])
    reached = np.flatnonzero(probe["hole_depth_m"] >= next_top_md_m + 4.0)
    k = int(reached[0]) if len(reached) else REPLAY_FALLBACK_LOSS
    if k < 900:
        raise ValueError("the next formation is less than 1.5 h of drilling ahead")
    loss = Planted("LOSS", k, 240, 1.1, end=k + 180)
    data = simulate(np.random.default_rng([seed, 1]), start_md_m, k + 360, base, [balling, loss])
    return Episode(well, t0, data, [balling, loss], None, hole_in, None)
