"""Real-time drilling data, Déjà Vu signatures and alerts (B4: S12, S7b-d, S9).

`rt_sample` and `rt_score` are TimescaleDB hypertables (migration 0007). They are *wide*:
one row per wellbore and timestamp with a column per canonical channel, rather than one
row per channel (BACKEND_PLAN V-B25): 12x fewer rows and one-row reads for the live view.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Canonical channels (SI), in the order of the rt_sample columns.
CHANNELS: tuple[str, ...] = (
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


class RtSample(Base):
    __tablename__ = "rt_sample"
    wellbore_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    bit_depth_m: Mapped[float | None] = mapped_column(Float)
    hole_depth_m: Mapped[float | None] = mapped_column(Float)
    hookload_kn: Mapped[float | None] = mapped_column(Float)
    wob_kn: Mapped[float | None] = mapped_column(Float)
    rpm: Mapped[float | None] = mapped_column(Float)
    torque_knm: Mapped[float | None] = mapped_column(Float)
    spp_kpa: Mapped[float | None] = mapped_column(Float)
    flow_in_lpm: Mapped[float | None] = mapped_column(Float)
    flow_out_lpm: Mapped[float | None] = mapped_column(Float)
    pit_volume_m3: Mapped[float | None] = mapped_column(Float)
    rop_m_h: Mapped[float | None] = mapped_column(Float)
    gas_pct: Mapped[float | None] = mapped_column(Float)
    quality: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # channel → flag
    session_id: Mapped[int | None] = mapped_column(Integer)


class RtScore(Base):
    """What the scoring loop concluded at a timestamp: rig state, indicators, scores."""

    __tablename__ = "rt_score"
    wellbore_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    rig_state: Mapped[str] = mapped_column(String(20))
    bit_depth_m: Mapped[float | None] = mapped_column(Float)
    formation: Mapped[str | None] = mapped_column(Text)
    indicators: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    scores: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # event type → prob
    dejavu: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    session_id: Mapped[int | None] = mapped_column(Integer)


class ChannelMapping(Base):
    """Source mnemonic → canonical channel and the unit the source sends it in."""

    __tablename__ = "channel_mapping"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(20))  # csv | wits0 | witsml
    mnemonic: Mapped[str] = mapped_column(String(40))
    channel: Mapped[str] = mapped_column(String(40))
    unit: Mapped[str] = mapped_column(String(20))


class ReplaySession(Base):
    __tablename__ = "replay_session"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("well.id", ondelete="CASCADE"))
    wellbore_id: Mapped[int] = mapped_column(ForeignKey("wellbore.id", ondelete="CASCADE"))
    source_uri: Mapped[str] = mapped_column(Text)
    speed: Mapped[float] = mapped_column(Float, default=60.0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    position: Mapped[int] = mapped_column(Integer, default=0)  # rows published
    total_rows: Mapped[int | None] = mapped_column(Integer)
    data_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_now: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PatternSignature(Base):
    """The real-time window that preceded a historical event (Déjà Vu library, S7d)."""

    __tablename__ = "pattern_signature"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("event.id", ondelete="SET NULL"))
    well_id: Mapped[int] = mapped_column(ForeignKey("well.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(20))
    formation: Mapped[str | None] = mapped_column(Text)
    hole_size_in: Mapped[float | None] = mapped_column(Float)
    md_m: Mapped[float | None] = mapped_column(Float)
    tvdss_m: Mapped[float | None] = mapped_column(Float)
    dt_s: Mapped[int] = mapped_column(Integer, default=10)
    channels: Mapped[dict[str, list[float]]] = mapped_column(JSONB)
    drilling_share: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(20), default="synthetic")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Alert(Base):
    __tablename__ = "alert"
    __table_args__ = (Index("ix_alert_well_id_status", "well_id", "status"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    well_id: Mapped[int] = mapped_column(ForeignKey("well.id", ondelete="CASCADE"))
    wellbore_id: Mapped[int | None] = mapped_column(Integer)
    session_id: Mapped[int | None] = mapped_column(Integer)
    alert_type: Mapped[str] = mapped_column(String(20))  # LOOKAHEAD | ANOMALY_ML | ...
    event_type: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(10))  # info | warning | critical
    status: Mapped[str] = mapped_column(String(12), default="new")
    title: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(Float)
    score_kind: Mapped[str] = mapped_column(String(12))  # probability | similarity | ...
    md_m: Mapped[float | None] = mapped_column(Float)
    tvdss_m: Mapped[float | None] = mapped_column(Float)
    formation: Mapped[str | None] = mapped_column(Text)
    t_data: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sources: Mapped[list[str]] = mapped_column(JSONB, default=list)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    drivers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    recommendations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    budget_exempt: Mapped[bool] = mapped_column(Boolean, default=False)
    acked_by: Mapped[str | None] = mapped_column(Text)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismiss_reason: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AlertFeedback(Base):
    __tablename__ = "alert_feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alert.id", ondelete="CASCADE"))
    verdict: Mapped[str] = mapped_column(String(20))  # useful | not_useful | false_alarm
    comment: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
