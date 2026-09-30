"""Per-well scoring loop (S7b-d over the S12 stream): one call per incoming sample.

For each sample: rig state, bit TVDSS and formation, the physics indicators. Every minute
of data: the classifiers (with hysteresis) and the look-ahead check. Every 3 minutes of
data: Déjà Vu. Out come a frame for the live view and alert candidates for the engine.

Pure over its inputs (no database, no Redis): the stream service builds the context.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from app.alerts.engine import Candidate, severity_for
from app.physics.indicators import ThresholdDetector
from app.risk import dejavu as dv
from app.risk import features as feats
from app.risk.realtime_model import ModelBundle
from app.risk.rigstate import RigStateMachine
from app.stream.quality import UNFIT, QualityMonitor
from app.synthetic.realtime import CHANNELS, DT_S

BUFFER = 900  # 2.5 h of 10-s samples: features need 1 h, Déjà Vu 30 min
ML_EVERY = 6  # 1 min
DV_EVERY = 18  # 3 min
ML_CONSECUTIVE = 2
ML_CLEAR = 0.8  # clear below 0.8 x threshold
DV_CONSECUTIVE = 2
LOOKAHEAD_TVD_M = 30.0  # about 2 h of drilling at a typical 8-1/2" ROP
LOOKAHEAD_MIN_P = 0.3
IMBALANCE_PCT = 5.0
PIT_M3 = 0.8
PIT_WINDOW = 90  # 15 min
STREAM_EVIDENCE = timedelta(minutes=30)
EVENT_LABELS = {
    "LOSS": "losses",
    "KICK": "a kick",
    "STUCK": "stuck pipe",
    "TIGHT": "tight hole",
    "TORQUE": "high torque",
    "BALLING": "bit balling",
    "INSTAB": "hole instability",
    "OVERP": "overpressure",
    "GAS": "gas",
    "CEMENT": "cementing problems",
}
DRIVER_CHANNELS = {
    "imb": ["flow_in_lpm", "flow_out_lpm"],
    "pit": ["pit_volume_m3"],
    "torque": ["torque_knm"],
    "hook": ["hookload_kn"],
    "overpull": ["hookload_kn"],
    "rop": ["rop_m_h"],
    "wob": ["wob_kn"],
    "spp": ["spp_kpa"],
    "gas": ["gas_pct"],
    "mse": ["torque_knm", "rop_m_h", "wob_kn"],
    "drilling": ["wob_kn"],
}


@dataclass
class Interval:
    formation: str
    top_md_m: float
    top_tvdss_m: float
    prognosed: bool
    risks: dict[str, float]  # event type -> prior probability
    offset_events: dict[str, list[int]]  # event type -> offsets' event ids (evidence)


@dataclass
class WellContext:
    well_id: int
    wellbore_id: int
    name: str
    hole_size_in: float
    station_md: np.ndarray
    station_tvdss: np.ndarray
    last_inc_deg: float
    intervals: list[Interval]

    def tvdss_at(self, md: float) -> float | None:
        if not len(self.station_md):
            return None
        if md <= self.station_md[-1]:
            return float(np.interp(md, self.station_md, self.station_tvdss))
        cos_inc = max(float(np.cos(np.radians(self.last_inc_deg))), 0.2)
        return float(self.station_tvdss[-1] + (md - self.station_md[-1]) * cos_inc)

    def interval_at(self, tvdss: float | None) -> Interval | None:
        if tvdss is None:
            return None
        cur = None
        for iv in self.intervals:
            if iv.top_tvdss_m <= tvdss:
                cur = iv
        return cur

    def next_interval(self, tvdss: float | None) -> Interval | None:
        if tvdss is None:
            return None
        return next((iv for iv in self.intervals if iv.top_tvdss_m > tvdss), None)


@dataclass
class Frame:
    ts: datetime
    values: dict[str, float | None]
    rig_state: str
    bit_depth_m: float | None
    bit_tvdss_m: float | None
    formation: str | None
    indicators: dict[str, float | None]
    scores: dict[str, float] | None = None  # set on the minutes the classifiers ran
    dejavu: dict[str, Any] | None = None  # set when Déjà Vu ran
    quality: dict[str, str] = field(default_factory=dict)  # channel → data-quality flag

    def to_json(self) -> dict[str, Any]:
        return {
            "ts": self.ts.isoformat(),
            "values": self.values,
            "rig_state": self.rig_state,
            "bit_depth_m": self.bit_depth_m,
            "bit_tvdss_m": self.bit_tvdss_m,
            "formation": self.formation,
            "indicators": self.indicators,
            "scores": self.scores,
            "dejavu": self.dejavu,
            "quality": self.quality,
        }


@dataclass
class WellScorer:
    ctx: WellContext
    bundle: ModelBundle | None
    library: list[dv.Signature]
    tau: float | None
    buf: dict[str, deque[float]] = field(default_factory=dict)
    times: deque[datetime] = field(default_factory=lambda: deque(maxlen=BUFFER))
    rig: RigStateMachine = field(default_factory=lambda: RigStateMachine(dt_s=DT_S))
    n: int = 0
    latest_scores: dict[str, float] = field(default_factory=dict)
    _ml_run: dict[str, int] = field(default_factory=dict)
    _ml_active: set[str] = field(default_factory=set)
    _dv_last: tuple[str, int] | None = None  # (event type, consecutive hits)
    _dv_active: str | None = None
    _lookahead_done: set[str] = field(default_factory=set)
    _loss_det: ThresholdDetector = field(
        default_factory=lambda: ThresholdDetector(IMBALANCE_PCT, 3.0, 6)
    )
    _kick_det: ThresholdDetector = field(
        default_factory=lambda: ThresholdDetector(IMBALANCE_PCT, 3.0, 6)
    )
    _pit_gain_det: ThresholdDetector = field(
        default_factory=lambda: ThresholdDetector(PIT_M3, PIT_M3 / 2, 3)
    )
    _pit_loss_det: ThresholdDetector = field(
        default_factory=lambda: ThresholdDetector(PIT_M3, PIT_M3 / 2, 3)
    )

    quality_monitor: QualityMonitor = field(default_factory=QualityMonitor)
    _flags: dict[str, str] = field(default_factory=dict)

    def _unfit(self) -> set[str]:
        return {ch for ch, f in self._flags.items() if f in UNFIT}

    def __post_init__(self) -> None:
        self.buf = {c: deque(maxlen=BUFFER) for c in CHANNELS}

    # ─── helpers ──────────────────────────────────────────────────────────

    def _arrays(self, last: int | None = None) -> dict[str, np.ndarray]:
        if last is None:
            return {c: np.asarray(v, dtype=float) for c, v in self.buf.items()}
        return {c: np.asarray(list(v)[-last:], dtype=float) for c, v in self.buf.items()}

    def _stream_evidence(self, ts: datetime, channels: list[str]) -> dict[str, Any]:
        return {
            "kind": "stream",
            "wellbore_id": self.ctx.wellbore_id,
            "t_from": (ts - STREAM_EVIDENCE).isoformat(),
            "t_to": ts.isoformat(),
            "channels": sorted(set(channels)),
        }

    def _offset_evidence(self, iv: Interval | None, event_type: str) -> list[dict[str, Any]]:
        if iv is None:
            return []
        ids = iv.offset_events.get(event_type, [])[:3]
        return [{"kind": "offset_event", "event_id": i, "formation": iv.formation} for i in ids]

    # ─── the loop ─────────────────────────────────────────────────────────

    def push(self, ts: datetime, values: dict[str, float | None]) -> tuple[Frame, list[Candidate]]:
        for c in CHANNELS:
            v = values.get(c)
            if v is None:  # a gap: hold the last value in the buffer (quality says so)
                v = self.buf[c][-1] if self.buf[c] else 0.0
            self.buf[c].append(float(v))
        self.times.append(ts)
        self.n += 1
        b = {c: self.buf[c][-1] for c in CHANNELS}
        state = self.rig.update(
            b["bit_depth_m"], b["hole_depth_m"], b["hookload_kn"], b["wob_kn"], b["rpm"],
            b["flow_in_lpm"],
        )  # fmt: skip
        md = values.get("bit_depth_m")
        tvdss = self.ctx.tvdss_at(b["hole_depth_m"])
        bit_tvdss = self.ctx.tvdss_at(b["bit_depth_m"])
        iv = self.ctx.interval_at(tvdss)
        cands: list[Candidate] = []
        self._flags = self.quality_monitor.update(values, state)
        indicators = self._physics(ts, state, tvdss, iv, cands)
        frame = Frame(
            ts, dict(values), state, md, bit_tvdss, iv.formation if iv else None, indicators
        )
        frame.quality = dict(self._flags)
        if self.n % ML_EVERY == 0:
            self._lookahead(ts, b["hole_depth_m"], tvdss, cands)
            if self.bundle is not None and len(self.times) > feats.MIN_HISTORY:
                frame.scores = self._ml(ts, tvdss, iv, cands)
        if (
            self.n % DV_EVERY == 0
            and self.library
            and self.tau
            and len(self.times) >= dv.QUERY_STEPS
        ):
            frame.dejavu = self._dejavu(ts, tvdss, iv, cands)
        for cand in cands:
            if cand.md_m is None:
                cand.md_m = round(b["hole_depth_m"], 1)
            if cand.tvdss_m is None:
                cand.tvdss_m = tvdss
            cand.formation = cand.formation or (iv.formation if iv else None)
        return frame, cands

    def _physics(
        self,
        ts: datetime,
        state: str,
        tvdss: float | None,
        iv: Interval | None,
        cands: list[Candidate],
    ) -> dict[str, float | None]:
        # A flow or pit channel flagged unfit (unit jump, out of range, flat-lined) must not
        # raise a kick or loss: bad data is shown as bad data, not as a well-control event.
        flow_ok = not ({"flow_in_lpm", "flow_out_lpm"} & self._unfit())
        pit_ok = "pit_volume_m3" not in self._unfit()
        fi = np.asarray(list(self.buf["flow_in_lpm"])[-12:])
        fo = np.asarray(list(self.buf["flow_out_lpm"])[-12:])
        pumping = fi > 200
        imb = (
            float(np.mean((fo[pumping] - fi[pumping]) / fi[pumping]) * 100)
            if pumping.sum() >= 6 and flow_ok
            else None
        )
        pit = list(self.buf["pit_volume_m3"])
        pit_d = pit[-1] - pit[-PIT_WINDOW] if len(pit) >= PIT_WINDOW and pit_ok else None
        out = {"flow_imbalance_pct": imb, "pit_change_15min_m3": pit_d}
        checks = [
            ("LOSS", self._loss_det, -imb if imb is not None else None, "return flow",
             f"returns {imb:.1f}% below flow in over 2 min" if imb is not None else ""),
            ("KICK", self._kick_det, imb, "return flow",
             f"returns {imb:.1f}% above flow in over 2 min" if imb is not None else ""),
            ("KICK", self._pit_gain_det, pit_d, "pit gain",
             f"pit volume up {pit_d:.2f} m3 in 15 min" if pit_d is not None else ""),
            ("LOSS", self._pit_loss_det, -pit_d if pit_d is not None else None, "pit loss",
             f"pit volume down {-pit_d:.2f} m3 in 15 min" if pit_d is not None else ""),
        ]  # fmt: skip
        for et, det, value, what, text in checks:
            if value is None:
                continue
            crossing = det.update(self.n, value)
            if crossing is None or crossing.kind != "raised":
                continue
            chans = ["pit_volume_m3"] if "pit" in what else ["flow_in_lpm", "flow_out_lpm"]
            cands.append(
                Candidate(
                    "PHYSICS",
                    et,
                    severity_for(et, strong=True),
                    round(value, 3),
                    "indicator",
                    ts,
                    f"Possible {EVENT_LABELS[et]}: {what}",
                    f"{text[0].upper()}{text[1:]} ({state.lower().replace('_', ' ')}). "
                    "A rule on the drilling channels, not a diagnosis: check the well.",
                    evidence=[self._stream_evidence(ts, chans), *self._offset_evidence(iv, et)],
                    detail={"rule": what, "threshold": det.on},
                )
            )
        return out

    def _ml(
        self, ts: datetime, tvdss: float | None, iv: Interval | None, cands: list[Candidate]
    ) -> dict[str, float]:
        assert self.bundle is not None
        d = self._arrays()
        x = feats.compute(d, np.array([len(self.times) - 1]), self.ctx.hole_size_in)[0]
        scores = self.bundle.score(x)
        self.latest_scores = scores
        for et, p in scores.items():
            thr = self.bundle.models[et].threshold
            if et in self._ml_active:
                if p < ML_CLEAR * thr:
                    self._ml_active.discard(et)
                continue
            self._ml_run[et] = self._ml_run.get(et, 0) + 1 if p >= thr else 0
            if self._ml_run[et] < ML_CONSECUTIVE:
                continue
            self._ml_active.add(et)
            self._ml_run[et] = 0
            drivers = self.bundle.drivers(x, et)
            chans = [
                ch
                for dr in drivers
                for key, cs in DRIVER_CHANNELS.items()
                if dr["feature"].startswith(key)
                for ch in cs
            ]
            top = ", ".join(dr["label"] for dr in drivers[:2]) or "several channels"
            cands.append(
                Candidate(
                    "ANOMALY_ML",
                    et,
                    severity_for(et, strong=p >= 0.5),
                    round(p, 3),
                    "probability",
                    ts,
                    f"{EVENT_LABELS[et].capitalize()} may be developing (next 30 min)",
                    f"Model probability {p:.0%} (alert threshold {thr:.0%}), driven by {top}. "
                    "Trained on SYNTHETIC data: advisory only.",
                    evidence=[
                        self._stream_evidence(ts, chans or ["torque_knm"]),
                        *self._offset_evidence(iv, et),
                    ],
                    drivers=drivers,
                    detail={"threshold": thr, "model": self.bundle.version, "horizon_min": 30},
                )
            )
        return {k: round(v, 4) for k, v in scores.items()}

    def _dejavu(
        self, ts: datetime, tvdss: float | None, iv: Interval | None, cands: list[Candidate]
    ) -> dict[str, Any]:
        assert self.tau is not None
        raw = self._arrays(dv.QUERY_STEPS)
        q = dv.prepare(raw)
        share = float(np.mean(raw["wob_kn"] > 10))
        matches = dv.search(
            q, self.library, self.tau, share, self.ctx.hole_size_in, exclude_well=self.ctx.well_id
        )
        if not matches:
            self._dv_last = None
            return {"matches": []}
        best = matches[0]
        out = {
            "matches": [
                {
                    "signature_id": m.signature.id,
                    "event_type": m.signature.event_type,
                    "event_id": m.signature.event_id,
                    "well_id": m.signature.well_id,
                    "similarity": round(m.similarity, 3),
                    "minutes_before_event": round(m.minutes_before_event, 1),
                }
                for m in matches
            ]
        }
        et = best.signature.event_type
        if best.similarity < dv.ALERT_SIMILARITY:
            self._dv_last = None
            if self._dv_active and best.similarity < dv.ALERT_SIMILARITY * 0.9:
                self._dv_active = None
            return out
        hits = self._dv_last[1] + 1 if self._dv_last and self._dv_last[0] == et else 1
        self._dv_last = (et, hits)
        if hits < DV_CONSECUTIVE or self._dv_active == et:
            return out
        self._dv_active = et
        meta = best.signature.meta or {}
        evidence: list[dict[str, Any]] = [
            self._stream_evidence(ts, ["torque_knm", "hookload_kn", "spp_kpa", "rop_m_h",
                                       "flow_out_lpm", "pit_volume_m3", "gas_pct"]),
        ]  # fmt: skip
        if best.signature.event_id is not None:
            evidence.append({"kind": "matched_event", "event_id": best.signature.event_id})
        cands.append(
            Candidate(
                "DEJA_VU",
                et,
                severity_for(et, strong=best.similarity >= 0.9),
                round(best.similarity, 3),
                "similarity",
                ts,
                f"The last 30 min resemble the run-up to past {EVENT_LABELS[et]}",
                f"Similarity {best.similarity:.2f} (not a probability) to the "
                f"{best.minutes_before_event:.0f} min before a {et} in "
                f"{meta.get('formation') or 'another well'}. Compare the charts before acting.",
                evidence=evidence,
                detail={
                    "matches": out["matches"],
                    "tau": self.tau,
                    "matched_signature_id": best.signature.id,
                    "matched_well_id": best.signature.well_id,
                },
            )
        )
        return out

    def _lookahead(
        self, ts: datetime, hole_md: float, tvdss: float | None, cands: list[Candidate]
    ) -> None:
        nxt = self.ctx.next_interval(tvdss)
        if nxt is None or tvdss is None or nxt.formation in self._lookahead_done:
            return
        dist = nxt.top_tvdss_m - tvdss
        if dist > LOOKAHEAD_TVD_M:
            return
        self._lookahead_done.add(nxt.formation)
        for et, p in sorted(nxt.risks.items(), key=lambda kv: -kv[1]):
            if p < LOOKAHEAD_MIN_P:
                continue
            prog = " (prognosed from offsets)" if nxt.prognosed else ""
            cands.append(
                Candidate(
                    "LOOKAHEAD",
                    et,
                    severity_for(et, strong=p >= 0.5),
                    round(p, 3),
                    "prior",
                    ts,
                    f"{nxt.formation} in about {dist:.0f} m TVD: offsets had {EVENT_LABELS[et]}",
                    f"The {nxt.formation} top{prog} is {dist:.0f} m below the bit. Offset "
                    f"prior {p:.0%} for {EVENT_LABELS[et]} there. Review the mitigations.",
                    md_m=round(nxt.top_md_m, 1),
                    tvdss_m=round(nxt.top_tvdss_m, 1),
                    formation=nxt.formation,
                    evidence=self._offset_evidence(nxt, et),
                    detail={"distance_tvd_m": round(dist, 1), "prognosed": nxt.prognosed},
                )
            )
