"""S2 engineering records: drilling events (+ evidence, mitigations), casing, cement, mud,
DDR operation lines and the review queue (migration 0005).

Every extracted record carries ``confidence`` (0..1), ``verified`` and its evidence
(``document_id`` + ``page_no`` + ``span_ids``), so the API can honour "no citation, no claim".
Depths are canonical metres named by reference (``md_m``/``tvd_m``/``tvdss_m``). Casing
``od_in``/``hole_size_in``/``weight_ppf`` are the industry's nominal size designations
(``9 5/8"``, ``47 ppf``), kept as labels, not measurements converted to SI.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.vocab import (
    CEMENT_RETURNS,
    EVENT_SOURCES,
    EVENT_STATUSES,
    EVENT_TYPES,
    EVIDENCE_ROLES,
    MITIGATION_OUTCOMES,
    REVIEW_KINDS,
    REVIEW_STATUSES,
    SEVERITIES,
    in_list,
)

CONFIDENCE_RANGE = "confidence >= 0 AND confidence <= 1"


class EvidenceMixin:
    """Evidence and trust columns shared by casing, cement, mud and mitigation rows.

    ``document_id`` is null only for manually entered records; ``span_ids`` point at
    ``text_span`` rows of ``page_no`` in that document.
    """

    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    page_no: Mapped[int | None] = mapped_column(Integer)
    span_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), default=list, server_default=text("'{}'")
    )
    confidence: Mapped[float] = mapped_column(Float)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class Event(Base):
    """One drilling problem (master plan Stage 2 taxonomy) linked to well, depth and formation."""

    __tablename__ = "event"
    __table_args__ = (
        CheckConstraint(in_list("event_type", EVENT_TYPES), name="event_type"),
        CheckConstraint(in_list("severity", SEVERITIES), name="severity"),
        CheckConstraint(in_list("source", EVENT_SOURCES), name="source"),
        CheckConstraint(in_list("status", EVENT_STATUSES), name="status"),
        CheckConstraint(CONFIDENCE_RANGE, name="confidence"),
        Index("ix_event_well_id_md_m", "well_id", "md_m"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Denormalised from wellbore for the common "events of well X" filter.
    well_id: Mapped[int] = mapped_column(ForeignKey("well.id", ondelete="CASCADE"))
    # Null when the report does not say which hole (original / sidetrack) the event was in.
    wellbore_id: Mapped[int | None] = mapped_column(
        ForeignKey("wellbore.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(20), index=True)
    subtype: Mapped[str | None] = mapped_column(String(40))
    severity: Mapped[str | None] = mapped_column(String(10))
    t_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    t_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_date: Mapped[date | None] = mapped_column(Date, index=True)
    md_m: Mapped[float | None] = mapped_column(Float)
    tvd_m: Mapped[float | None] = mapped_column(Float)
    tvdss_m: Mapped[float | None] = mapped_column(Float)
    formation_id: Mapped[int | None] = mapped_column(
        ForeignKey("formation.id", ondelete="SET NULL"), index=True
    )
    hole_size_in: Mapped[float | None] = mapped_column(Float)
    mw_sg: Mapped[float | None] = mapped_column(Float)
    # Type-specific canonical-unit numbers, keys as in api.v1.schemas.events.EventParams.
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    cause_text: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    npt_hours: Mapped[float | None] = mapped_column(Float)
    resolved: Mapped[bool | None] = mapped_column(Boolean)
    # problem / likely_cause / action_taken / outcome / lesson (api LessonCardContent)
    lesson_card: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    confidence: Mapped[float] = mapped_column(Float)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    verified_by: Mapped[str | None] = mapped_column(String(100))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(
        String(10), default="active", server_default=text("'active'")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    evidence: Mapped[list["EventEvidence"]] = relationship(
        cascade="all, delete-orphan", order_by="EventEvidence.span_id"
    )
    mitigations: Mapped[list["Mitigation"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", order_by="Mitigation.seq"
    )


class EventEvidence(Base):
    """Links an event to the text spans that state it. ``document_id``/``page_no`` are
    denormalised from the span so evidence lists need no join through page."""

    __tablename__ = "event_evidence"
    __table_args__ = (CheckConstraint(in_list("role", EVIDENCE_ROLES), name="role"),)

    event_id: Mapped[int] = mapped_column(
        ForeignKey("event.id", ondelete="CASCADE"), primary_key=True
    )
    span_id: Mapped[int] = mapped_column(
        ForeignKey("text_span.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    page_no: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(
        String(10), default="primary", server_default=text("'primary'")
    )


class Mitigation(EvidenceMixin, Base):
    """An action taken against an event, in the order tried (``seq``), with its outcome.
    ``action_code`` is validated against app.db.vocab.ACTION_CODES by the application (no
    CHECK: the vocabulary grows with docs/taxonomy.md without a migration)."""

    __tablename__ = "mitigation"
    __table_args__ = (
        UniqueConstraint("event_id", "seq"),
        CheckConstraint(in_list("outcome", MITIGATION_OUTCOMES), name="outcome"),
        CheckConstraint(CONFIDENCE_RANGE, name="confidence"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer, default=1)
    action_code: Mapped[str] = mapped_column(String(40), index=True)
    action_text: Mapped[str | None] = mapped_column(Text)
    t_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(
        String(10), default="unknown", server_default=text("'unknown'")
    )
    npt_hours_after: Mapped[float | None] = mapped_column(Float)
    volume_lost_m3: Mapped[float | None] = mapped_column(Float)
    recurrence: Mapped[bool | None] = mapped_column(Boolean)

    event: Mapped[Event] = relationship(back_populates="mitigations")


class CasingString(EvidenceMixin, Base):
    __tablename__ = "casing_string"
    __table_args__ = (CheckConstraint(CONFIDENCE_RANGE, name="confidence"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    wellbore_id: Mapped[int] = mapped_column(
        ForeignKey("wellbore.id", ondelete="CASCADE"), index=True
    )
    od_in: Mapped[float | None] = mapped_column(Float)
    hole_size_in: Mapped[float | None] = mapped_column(Float)
    shoe_md_m: Mapped[float | None] = mapped_column(Float)
    shoe_tvd_m: Mapped[float | None] = mapped_column(Float)
    shoe_tvdss_m: Mapped[float | None] = mapped_column(Float)
    planned_shoe_md_m: Mapped[float | None] = mapped_column(Float)
    grade: Mapped[str | None] = mapped_column(String(20))
    weight_ppf: Mapped[float | None] = mapped_column(Float)

    cement_jobs: Mapped[list["CementJob"]] = relationship(
        back_populates="casing", cascade="all, delete-orphan", order_by="CementJob.id"
    )


class CementJob(EvidenceMixin, Base):
    __tablename__ = "cement_job"
    __table_args__ = (
        CheckConstraint(in_list("returns", CEMENT_RETURNS), name="returns"),
        CheckConstraint(CONFIDENCE_RANGE, name="confidence"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    casing_id: Mapped[int] = mapped_column(
        ForeignKey("casing_string.id", ondelete="CASCADE"), index=True
    )
    toc_md_m: Mapped[float | None] = mapped_column(Float)  # top of cement
    toc_tvdss_m: Mapped[float | None] = mapped_column(Float)
    returns: Mapped[str | None] = mapped_column(String(10))
    slurry_density_sg: Mapped[float | None] = mapped_column(Float)
    volume_m3: Mapped[float | None] = mapped_column(Float)
    bond_quality: Mapped[str | None] = mapped_column(Text)
    remedial: Mapped[str | None] = mapped_column(Text)

    casing: Mapped[CasingString] = relationship(back_populates="cement_jobs")


class MudInterval(EvidenceMixin, Base):
    __tablename__ = "mud_interval"
    __table_args__ = (
        CheckConstraint(CONFIDENCE_RANGE, name="confidence"),
        Index("ix_mud_interval_wellbore_id_md_from_m", "wellbore_id", "md_from_m"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    wellbore_id: Mapped[int] = mapped_column(ForeignKey("wellbore.id", ondelete="CASCADE"))
    md_from_m: Mapped[float] = mapped_column(Float)
    md_to_m: Mapped[float] = mapped_column(Float)
    tvdss_from_m: Mapped[float | None] = mapped_column(Float)
    tvdss_to_m: Mapped[float | None] = mapped_column(Float)
    hole_size_in: Mapped[float | None] = mapped_column(Float)
    mud_type: Mapped[str | None] = mapped_column(String(40))
    mw_sg: Mapped[float | None] = mapped_column(Float)
    ecd_sg: Mapped[float | None] = mapped_column(Float)


class DdrOperation(Base):
    """One line of a daily drilling report's time log. NPT lines link to the event they
    describe; the timeline is also the label source for the real-time models (B4)."""

    __tablename__ = "ddr_operation"
    __table_args__ = (Index("ix_ddr_operation_wellbore_id_t_from", "wellbore_id", "t_from"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    wellbore_id: Mapped[int] = mapped_column(ForeignKey("wellbore.id", ondelete="CASCADE"))
    document_id: Mapped[int] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    page_no: Mapped[int | None] = mapped_column(Integer)
    report_date: Mapped[date | None] = mapped_column(Date)
    t_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    t_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hours: Mapped[float | None] = mapped_column(Float)
    md_m: Mapped[float | None] = mapped_column(Float)
    activity_code: Mapped[str | None] = mapped_column(String(40))
    phase: Mapped[str | None] = mapped_column(String(30))  # operation phase, e.g. DRILLING
    description: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    is_npt: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    npt_category: Mapped[str | None] = mapped_column(String(30))
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("event.id", ondelete="SET NULL"), index=True
    )
    span_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), default=list, server_default=text("'{}'")
    )


class ReviewItem(Base):
    """A low-confidence extraction (or alias match) awaiting a human decision.

    ``target_id`` is the row in the table named by ``kind`` (null when the proposal has not
    been written anywhere yet); ``proposed`` holds the extracted values, ``correction`` the
    reviewer's replacement values. Accepted and corrected items mark the target verified.
    """

    __tablename__ = "review_item"
    __table_args__ = (
        CheckConstraint(in_list("kind", REVIEW_KINDS), name="kind"),
        CheckConstraint(in_list("status", REVIEW_STATUSES), name="status"),
        CheckConstraint(CONFIDENCE_RANGE, name="confidence"),
        Index("ix_review_item_status_kind", "status", "kind"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[int | None] = mapped_column(BigInteger)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    page_no: Mapped[int | None] = mapped_column(Integer)
    span_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), default=list, server_default=text("'{}'")
    )
    field: Mapped[str | None] = mapped_column(String(60))  # null = the whole record
    reason: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    proposed: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(10), default="pending", server_default=text("'pending'")
    )
    decided_by: Mapped[str | None] = mapped_column(String(100))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    correction: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
