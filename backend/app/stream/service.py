"""The stream service (S12 + S9): ``python -m app.stream.run``.

- A **publisher** thread per replay session reads the source (a CSV in object storage, or a
  WITS0 TCP feed), converts every record to canonical channels through ``channel_mapping``,
  and XADDs it to ``rt:{wellbore_id}``, paced at the session's speed.
- A **consumer** reads each stream with two Redis consumer groups: ``persist`` batches the
  samples into ``rt_sample``; ``score`` runs the well's scorer, writes ``rt_score``, XADDs
  a frame to ``scores:{wellbore_id}`` (the live view) and passes alert candidates through
  the alert engine: created or fused alerts are stored with evidence and ledger
  recommendations and announced on the ``alerts`` stream.
"""

import csv
import io
import json
import logging
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import redis
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.alerts.engine import SEVERITY_RANK, AlertEngine, Candidate, Decision
from app.core import metrics
from app.core.config import get_settings
from app.db.models import Event, Well
from app.db.models.realtime import CHANNELS, Alert, ReplaySession, RtSample, RtScore
from app.db.session import session_scope
from app.extract.evidence import event_evidence_refs
from app.risk import assets
from app.stream import mapping as mp
from app.stream import wits0
from app.stream.context import build_context
from app.stream.scorer import WellScorer

log = logging.getLogger(__name__)

ALERTS_KEY = "alerts"
HEARTBEAT_KEY = "stream:heartbeat"
GROUPS = ("persist", "score")
STREAM_MAXLEN = 20_000
SCORES_MAXLEN = 5_000
POSITION_EVERY = 30  # rows between replay_session position updates
LEDGER_RADIUS_KM = 10.0


def rt_key(wellbore_id: int) -> str:
    return f"rt:{wellbore_id}"


def scores_key(wellbore_id: int) -> str:
    return f"scores:{wellbore_id}"


def get_redis() -> "redis.Redis":
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)


# ─── Publisher ────────────────────────────────────────────────────────────────


def _records(source_uri: str, skip: int) -> tuple[str, Iterator[dict[str, str]], int | None]:
    """(mapping source, raw records from row `skip` on, total rows if known)."""
    if source_uri.startswith("wits0://"):
        host, _, port = source_uri.removeprefix("wits0://").partition(":")
        return "wits0", wits0.read(host, int(port or 2000)), None
    key = source_uri.removeprefix(f"s3://{get_settings().s3_bucket_raw}/")
    rows = list(csv.DictReader(io.StringIO(assets.get_object(key).decode())))
    return "csv", iter(rows[skip:]), len(rows)


class Publisher(threading.Thread):
    def __init__(self, session_id: int, r: "redis.Redis") -> None:
        super().__init__(daemon=True, name=f"publisher-{session_id}")
        self.session_id = session_id
        self.r = r

    def _state(self) -> tuple[str, float]:
        with session_scope() as s:
            rs = s.get(ReplaySession, self.session_id)
            return (rs.status, rs.speed) if rs else ("stopped", 1.0)

    def run(self) -> None:
        try:
            self._run()
        except Exception as exc:  # the session records it; the service keeps running
            log.exception("replay session %s failed", self.session_id)
            with session_scope() as s:
                rs = s.get(ReplaySession, self.session_id)
                if rs:
                    rs.status, rs.error = "failed", f"{type(exc).__name__}: {exc}"[:500]

    def _run(self) -> None:
        with session_scope() as s:
            rs = s.get(ReplaySession, self.session_id)
            if rs is None:
                return
            wb, uri, position = rs.wellbore_id, rs.source_uri, rs.position
            rs.status = "running"
        kind, records, total = _records(uri, position)
        with session_scope() as s:
            maps = assets.load_mappings(s, kind)
            rs = s.get(ReplaySession, self.session_id)
            if rs is not None and total is not None:
                rs.total_rows = total
        key = rt_key(wb)
        anchor_wall: float | None = None
        anchor_data: datetime | None = None
        status, speed = "running", 1.0
        checked = 0.0
        i = position
        for rec in records:
            now = time.monotonic()
            if now - checked > 1.0:  # follow pause / stop / speed changes about once a second
                checked = now
                status, new_speed = self._state()
                while status == "paused":
                    time.sleep(0.5)
                    status, new_speed = self._state()
                    anchor_wall = None
                if status not in ("running", "pending"):
                    return
                if new_speed != speed:
                    speed, anchor_wall = new_speed, None
            values, quality = mp.to_canonical(rec, maps)
            ts = (
                mp.parse_time(str(rec[mp.TIME_COLUMN]))
                if kind == "csv"
                else datetime.now(tz=UTC).replace(microsecond=0)
            )
            if kind == "csv":
                if anchor_wall is None or anchor_data is None:
                    anchor_wall, anchor_data = time.monotonic(), ts
                wait = anchor_wall + (ts - anchor_data).total_seconds() / speed - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
            self.r.xadd(
                key,
                {
                    "ts": ts.isoformat(),
                    "sid": str(self.session_id),
                    "v": json.dumps(values),
                    "q": json.dumps(quality),
                    "pub": f"{time.time():.3f}",
                },
                maxlen=STREAM_MAXLEN,
                approximate=True,
            )
            i += 1
            if i % POSITION_EVERY == 0:
                self._position(i, ts)
        self._position(i, None, finished=True)

    def _position(self, i: int, ts: datetime | None, finished: bool = False) -> None:
        with session_scope() as s:
            rs = s.get(ReplaySession, self.session_id)
            if rs is None:
                return
            rs.position = i
            if ts is not None:
                rs.data_now = ts
                rs.data_start = rs.data_start or ts
            if finished and rs.status == "running":
                rs.status = "finished"


# ─── Consumer ─────────────────────────────────────────────────────────────────


@dataclass
class _Live:
    session_id: int
    well_id: int
    scorer: WellScorer
    engine: AlertEngine


def _enrich(session: Session, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resolve event references to their well and report pages (the click-through)."""
    ids = [int(e["event_id"]) for e in evidence if "event_id" in e]
    refs = event_evidence_refs(session, ids) if ids else {}
    rows = {
        r[0]: r
        for r in session.execute(
            select(Event.id, Event.well_id, Well.canonical_name, Event.event_type, Event.md_m)
            .join(Well, Well.id == Event.well_id)
            .where(Event.id.in_(ids or [-1]))
        ).all()
    }
    out = []
    for e in evidence:
        if "event_id" in e and e["event_id"] in rows:
            _, well_id, name, et, md = rows[e["event_id"]]
            e = {
                **e,
                "well_id": well_id,
                "well_name": name,
                "event_type": et,
                "md_m": md,
                "refs": [r.model_dump() for r in refs.get(e["event_id"], [])],
            }
        out.append(e)
    return out


def recommendations(
    session: Session, event_type: str, formation: str | None, well_id: int
) -> tuple[list[dict[str, Any]], str | None]:
    """What worked before (S8): the ledger's top actions for this problem nearby."""
    from app.ledger.service import ledger

    try:
        led = ledger(
            session,
            event_type=event_type,
            formation=formation,
            well_id=well_id,
            radius_km=LEDGER_RADIUS_KM,
        )
    except Exception:  # an unknown formation name: fall back to the neighbourhood
        led = ledger(session, event_type=event_type, well_id=well_id, radius_km=LEDGER_RADIUS_KM)
    picks = [(e, False) for e in led.ranked[:3]] or [(e, True) for e in led.insufficient[:2]]
    return [
        {
            "action_code": e.action_code,
            "action_label": e.action_label,
            "summary": e.summary,
            "n": e.n,
            "posterior_mean": e.posterior_mean,
            "ci90_low": e.ci90_low,
            "ci90_high": e.ci90_high,
            "insufficient": insufficient,
        }
        for e, insufficient in picks
    ], led.caveat


def store_candidate(
    session: Session, live: _Live, c: Candidate, d: Decision, published_at: float
) -> tuple[int, str] | None:
    """Apply an engine decision to the database; returns (alert id, created|fused)."""
    if d.action == "suppress":
        metrics.ALERTS_SUPPRESSED.labels(reason=d.reason).inc()
        return None
    evidence = _enrich(session, c.evidence)
    latency_ms = round((time.time() - published_at) * 1000, 1)
    if d.action == "create":
        recs, caveat = recommendations(session, c.event_type, c.formation, live.well_id)
        alert = Alert(
            well_id=live.well_id,
            wellbore_id=live.scorer.ctx.wellbore_id,
            session_id=live.session_id,
            alert_type=c.alert_type,
            event_type=c.event_type,
            severity=c.severity,
            status="new",
            title=c.title,
            message=c.message,
            score=c.score,
            score_kind=c.score_kind,
            md_m=c.md_m,
            tvdss_m=None if c.tvdss_m is None else round(c.tvdss_m, 1),
            formation=c.formation,
            t_data=c.t_data,
            sources=[c.alert_type],
            evidence=evidence,
            drivers=c.drivers,
            recommendations=recs,
            detail={**c.detail, "latency_ms": latency_ms, "ledger_caveat": caveat},
            budget_exempt=c.budget_exempt,
        )
        session.add(alert)
        session.flush()
        live.engine.created(alert.id, c)
        metrics.ALERTS_RAISED.labels(c.alert_type, c.severity, "created").inc()
        return alert.id, "created"
    assert d.target is not None
    target = session.get(Alert, d.target.id)
    if target is None:
        return None
    alert = target
    live.engine.fused(d.target, c)
    alert.alert_type = "FUSED"
    alert.sources = [*alert.sources, c.alert_type]
    alert.evidence = [*alert.evidence, *evidence]
    alert.drivers = [*alert.drivers, *c.drivers]
    if SEVERITY_RANK[c.severity] > SEVERITY_RANK[alert.severity]:
        alert.severity = c.severity
    fused = [
        *alert.detail.get("fused", []),
        {
            "source": c.alert_type,
            "score": c.score,
            "score_kind": c.score_kind,
            "t_data": c.t_data.isoformat(),
            "title": c.title,
            "message": c.message,
            "latency_ms": latency_ms,
            "detail": c.detail,  # e.g. the Déjà Vu match, for the overlay
        },
    ]
    alert.detail = {**alert.detail, "fused": fused}
    metrics.ALERTS_RAISED.labels(c.alert_type, c.severity, "fused").inc()
    return alert.id, "fused"


class Consumer:
    def __init__(self, r: "redis.Redis") -> None:
        self.r = r
        self.live: dict[int, _Live] = {}  # wellbore id -> scorer of the current session
        self.keys: set[str] = set()
        self._bundle: Any = None
        self._dejavu: tuple[list[Any], float | None] | None = None
        self.processed = 0

    def track(self, wellbore_id: int) -> None:
        key = rt_key(wellbore_id)
        if key in self.keys:
            return
        for g in GROUPS:
            try:
                self.r.xgroup_create(key, g, id="0", mkstream=True)
            except redis.ResponseError as exc:
                if "BUSYGROUP" not in str(exc):
                    raise
        self.keys.add(key)

    def _assets(self, session: Session) -> tuple[Any, list[Any], float | None]:
        if self._bundle is None:
            try:
                self._bundle = assets.load_bundle()
            except Exception:
                log.warning("no classifier bundle in object storage: ML scoring off")
                self._bundle = False
        if self._dejavu is None:
            try:
                self._dejavu = (assets.load_library(session), float(assets.load_dejavu()["tau"]))
            except Exception:
                log.warning("no Deja Vu calibration: pattern matching off")
                self._dejavu = ([], None)
        return self._bundle or None, self._dejavu[0], self._dejavu[1]

    def _live_for(self, session: Session, wellbore_id: int, session_id: int) -> _Live:
        cur = self.live.get(wellbore_id)
        if cur is not None and cur.session_id == session_id:
            return cur
        rs = session.get(ReplaySession, session_id)
        if rs is None:
            raise LookupError(f"replay session {session_id} not found")
        bundle, library, tau = self._assets(session)
        ctx = build_context(session, rs.well_id, wellbore_id)
        live = _Live(session_id, rs.well_id, WellScorer(ctx, bundle, library, tau), AlertEngine())
        self.live[wellbore_id] = live
        return live

    def step(self, block_ms: int = 500) -> int:
        """Read and process one batch per group; returns the messages handled."""
        if not self.keys:
            time.sleep(block_ms / 1000)
            return 0
        handled = 0
        for group in GROUPS:
            resp: Any = self.r.xreadgroup(
                group, "stream-1", dict.fromkeys(self.keys, ">"), count=500, block=block_ms
            )
            for key, messages in resp or []:
                if not messages:
                    continue
                wb = int(key.split(":", 1)[1])
                if group == "persist":
                    self._persist(wb, messages)
                else:
                    self._score(wb, messages)
                self.r.xack(key, group, *[m[0] for m in messages])
                handled += len(messages)
        self.processed += handled
        return handled

    def _persist(self, wb: int, messages: list[tuple[str, dict[str, str]]]) -> None:
        rows = []
        for _, f in messages:
            v = json.loads(f["v"])
            rows.append(
                {
                    "wellbore_id": wb,
                    "ts": datetime.fromisoformat(f["ts"]),
                    **{c: v.get(c) for c in CHANNELS},
                    "quality": json.loads(f["q"]) or None,
                    "session_id": int(f["sid"]),
                }
            )
        with session_scope() as s:
            s.execute(insert(RtSample).values(rows).on_conflict_do_nothing())

    def _score(self, wb: int, messages: list[tuple[str, dict[str, str]]]) -> None:
        with session_scope() as s:
            score_rows = []
            announcements: list[tuple[int, str, int]] = []
            for _, f in messages:
                live = self._live_for(s, wb, int(f["sid"]))
                ts = datetime.fromisoformat(f["ts"])
                frame, cands = live.scorer.push(ts, json.loads(f["v"]))
                score_rows.append(
                    {
                        "wellbore_id": wb,
                        "ts": ts,
                        "rig_state": frame.rig_state,
                        "bit_depth_m": frame.bit_depth_m,
                        "formation": frame.formation,
                        "indicators": frame.indicators,
                        "scores": frame.scores or {},
                        "dejavu": frame.dejavu,
                        "session_id": live.session_id,
                    }
                )
                for c in cands:
                    stored = store_candidate(s, live, c, live.engine.decide(c), float(f["pub"]))
                    if stored:
                        announcements.append((stored[0], stored[1], live.well_id))
                payload = frame.to_json()
                payload["latest_scores"] = live.scorer.latest_scores
                payload["session_id"] = live.session_id
                self.r.xadd(
                    scores_key(wb),
                    {"frame": json.dumps(payload)},
                    maxlen=SCORES_MAXLEN,
                    approximate=True,
                )
            s.execute(insert(RtScore).values(score_rows).on_conflict_do_nothing())
        for alert_id, action, well_id in announcements:  # after commit: readers see the row
            self.r.xadd(
                ALERTS_KEY,
                {"id": str(alert_id), "action": action, "well_id": str(well_id)},
                maxlen=SCORES_MAXLEN,
                approximate=True,
            )
        # How far behind the live view is: publish -> frame out, for the newest sample.
        metrics.SCORING_LAG.set(max(0.0, time.time() - float(messages[-1][1]["pub"])))
        metrics.SAMPLES_SCORED.inc(len(messages))

    def sync_alert_states(self) -> None:
        """Feed acks and dismissals made in the API back into the engines (cooldown)."""
        for live in self.live.values():
            ids = [a.id for a in live.engine.alerts if a.status == "new"]
            if not ids:
                continue
            with session_scope() as s:
                rows = s.execute(
                    select(Alert.id, Alert.status, Alert.updated_at).where(
                        Alert.id.in_(ids), Alert.status != "new"
                    )
                ).all()
            for alert_id, status, _ in rows:
                t_data = live.scorer.times[-1] if live.scorer.times else datetime.now(tz=UTC)
                live.engine.closed(alert_id, status, t_data)


# ─── Service ──────────────────────────────────────────────────────────────────


def reset_wellbore(session: Session, wellbore_id: int) -> None:
    """A new replay replaces the wellbore's earlier replayed samples (alerts are kept)."""
    session.execute(
        delete(RtSample).where(
            RtSample.wellbore_id == wellbore_id, RtSample.session_id.is_not(None)
        )
    )
    session.execute(delete(RtScore).where(RtScore.wellbore_id == wellbore_id))


class StreamService:
    def __init__(self, r: "redis.Redis | None" = None) -> None:
        self.r = r or get_redis()
        self.consumer = Consumer(self.r)
        self.publishers: dict[int, Publisher] = {}
        self._stop = threading.Event()

    def poll_sessions(self) -> None:
        cutoff = datetime.now(tz=UTC) - timedelta(hours=6)
        with session_scope() as s:
            rows = s.execute(
                select(ReplaySession.id, ReplaySession.wellbore_id, ReplaySession.status).where(
                    (ReplaySession.status.in_(("pending", "running", "paused")))
                    | (ReplaySession.updated_at >= cutoff)
                )
            ).all()
        for sid, wb, status in rows:
            self.consumer.track(wb)
            if status in ("pending", "running") and sid not in self.publishers:
                p = Publisher(sid, self.r)
                self.publishers[sid] = p
                p.start()
        for sid in [k for k, p in self.publishers.items() if not p.is_alive()]:
            del self.publishers[sid]

    def heartbeat(self) -> None:
        self.r.set(
            HEARTBEAT_KEY,
            json.dumps(
                {
                    "at": datetime.now(tz=UTC).isoformat(),
                    "publishers": sorted(self.publishers),
                    "streams": sorted(self.consumer.keys),
                    "processed": self.consumer.processed,
                }
            ),
            ex=15,
        )

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        last_poll = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            if now - last_poll > 1.0:
                last_poll = now
                self.poll_sessions()
                self.consumer.sync_alert_states()
                self.heartbeat()
            try:
                self.consumer.step()
            except Exception:
                log.exception("stream consumer step failed")
                time.sleep(1)
