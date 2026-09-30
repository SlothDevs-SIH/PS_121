"""S2 extraction service: parse one ingested report into engineering records.

For each document: parse (ddr.py / wcr.py), then write events with their evidence spans,
mitigations, casing + cement, mud intervals and DDR operation lines. Every record carries a
confidence and cites its spans; anything below ``extract_confidence_threshold`` also gets a
review-queue item saying why. The same event told by several reports (a DDR on the day,
the WCR at the end of the well) is merged into one event that cites all of them.

Idempotent: re-extracting a document first removes what that document contributed
(unverified records only; a human's verification is never undone by a re-run).
"""

import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import delete, exists, func, select, text, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.metrics import EXTRACTION_CONFIDENCE
from app.db.models import (
    CasingString,
    CementJob,
    DdrOperation,
    Document,
    Event,
    EventEvidence,
    FormationTop,
    Mitigation,
    MudInterval,
    Page,
    ReviewItem,
    SurveyStation,
    TextSpan,
    Wellbore,
)
from app.db.models import Formation as FormationRow
from app.db.vocab import ACTION_CODES
from app.extract import ddr, wcr
from app.extract.drafts import (
    CasingDraft,
    EventDraft,
    Line,
    MitigationDraft,
    MudDraft,
    ParsedDocument,
    ocr_confidence,
)

log = logging.getLogger("smriti.extract")

EXTRACTABLE = ("DDR", "WCR")
MERGE_DEPTH_M = 15.0  # same well + type within this depth and MERGE_DAYS = same event
MERGE_DAYS = 3
_LOCK_NAMESPACE = 121  # pg_advisory_xact_lock(namespace, well_id)


# ─── Inputs ────────────────────────────────────────────────────────────────────────────────


def load_lines(session: Session, document_id: int) -> list[Line]:
    rows = session.execute(
        select(Page.page_no, TextSpan.id, TextSpan.text, TextSpan.conf, TextSpan.bbox)
        .join(TextSpan, TextSpan.page_id == Page.id)
        .where(Page.document_id == document_id)
        .order_by(Page.page_no, TextSpan.line_no)
    ).all()
    return [
        Line(
            span_id=r.id,
            page_no=r.page_no,
            text=r.text,
            conf=r.conf,
            x0=float(r.bbox[0]),
            y=float(r.bbox[1] + r.bbox[3]) / 2,
        )
        for r in rows
    ]


class FormationResolver:
    """Finds formation names (and their synonyms) in free text; longest name wins."""

    def __init__(self, session: Session) -> None:
        names: list[tuple[str, int]] = []
        for f in session.scalars(select(FormationRow)):
            for n in (f.name, *(f.synonyms or [])):
                names.append((n, f.id))
        names.sort(key=lambda x: -len(x[0]))
        self._patterns = [
            (
                re.compile(
                    r"(?<![A-Za-z])" + re.escape(n) + r"(?![A-Za-z])",
                    0 if len(n) <= 3 else re.I,  # short codes (TPM, KPL) are case-sensitive
                ),
                fid,
            )
            for n, fid in names
        ]

    def find(self, text: str | None) -> int | None:
        if not text:
            return None
        return next((fid for p, fid in self._patterns if p.search(text)), None)


@dataclass
class WellContext:
    well_id: int
    wellbore_id: int | None  # the primary wellbore (casing, mud and DDR lines hang off it)
    single_wellbore: bool
    md: np.ndarray
    tvd: np.ndarray
    tvdss: np.ndarray
    tops: list[tuple[float, int]]  # (top MD, formation id), shallow first

    @classmethod
    def load(cls, session: Session, well_id: int) -> "WellContext":
        wbs = list(
            session.scalars(
                select(Wellbore).where(Wellbore.well_id == well_id).order_by(Wellbore.id)
            )
        )
        wb = wbs[0] if wbs else None
        st = (
            session.execute(
                select(SurveyStation.md_m, SurveyStation.tvd_m, SurveyStation.tvdss_m)
                .where(SurveyStation.wellbore_id == wb.id)
                .order_by(SurveyStation.md_m)
            ).all()
            if wb
            else []
        )
        tops = (
            session.execute(
                select(FormationTop.top_md_m, FormationTop.formation_id)
                .where(FormationTop.wellbore_id == wb.id)
                .order_by(FormationTop.top_md_m)
            ).all()
            if wb
            else []
        )
        return cls(
            well_id=well_id,
            wellbore_id=wb.id if wb else None,
            single_wellbore=len(wbs) == 1,
            md=np.array([r[0] for r in st], dtype=float),
            tvd=np.array([r[1] for r in st], dtype=float),
            tvdss=np.array([r[2] for r in st], dtype=float),
            tops=[(float(r[0]), int(r[1])) for r in tops],
        )

    def depth_refs(self, md: float | None) -> tuple[float | None, float | None]:
        """(TVD, TVDSS) at an MD, interpolated between survey stations; never extrapolated."""
        if md is None or len(self.md) < 2 or not self.md[0] <= md <= self.md[-1]:
            return None, None
        return (
            round(float(np.interp(md, self.md, self.tvd)), 1),
            round(float(np.interp(md, self.md, self.tvdss)), 1),
        )

    def formation_at(self, md: float | None) -> int | None:
        if md is None:
            return None
        found = None
        for top, fid in self.tops:
            if top <= md:
                found = fid
        return found


# ─── Cleanup (idempotency) ─────────────────────────────────────────────────────────────────


def clear_document(session: Session, document_id: int) -> None:
    """Remove what an earlier extraction of this document wrote (unverified records only)."""
    unverified = select(Event.id).where(Event.verified.is_(False))
    session.execute(
        delete(EventEvidence).where(
            EventEvidence.document_id == document_id, EventEvidence.event_id.in_(unverified)
        )
    )
    session.execute(
        delete(Mitigation).where(
            Mitigation.document_id == document_id,
            Mitigation.verified.is_(False),
            Mitigation.event_id.in_(unverified),
        )
    )
    # Rules-extracted events no document supports any more are gone with it.
    session.execute(
        delete(Event).where(
            Event.source.in_(("rules", "llm")),
            Event.verified.is_(False),
            ~exists().where(EventEvidence.event_id == Event.id),
        )
    )
    session.execute(delete(DdrOperation).where(DdrOperation.document_id == document_id))
    session.execute(
        delete(CasingString).where(
            CasingString.document_id == document_id, CasingString.verified.is_(False)
        )
    )
    session.execute(
        delete(MudInterval).where(
            MudInterval.document_id == document_id, MudInterval.verified.is_(False)
        )
    )
    session.execute(
        delete(ReviewItem).where(
            ReviewItem.document_id == document_id, ReviewItem.status == "pending"
        )
    )
    session.flush()


# ─── Main entry point ──────────────────────────────────────────────────────────────────────


def extract_document(session: Session, document_id: int) -> dict[str, Any]:
    doc = session.get(Document, document_id)
    if doc is None:
        raise ValueError(f"document {document_id} not found")
    skip = _skip_reason(doc)
    if skip:
        doc.extract_status, doc.extract_error = "skipped", skip
        doc.extracted_at = datetime.now(tz=UTC)
        session.flush()
        return {"document_id": doc.id, "status": "skipped", "reason": skip}
    assert doc.well_id is not None
    doc.extract_status, doc.extract_error = "running", None
    session.flush()
    # Serialise extraction per well so concurrent workers can't create duplicate events.
    session.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :wid)"), {"ns": _LOCK_NAMESPACE, "wid": doc.well_id}
    )
    clear_document(session, doc.id)

    lines = load_lines(session, doc.id)
    parsed: ParsedDocument = (ddr if doc.doc_type == "DDR" else wcr).parse(lines)
    ctx = WellContext.load(session, doc.well_id)
    resolver = FormationResolver(session)
    writer = _Writer(session, doc, ctx, resolver, get_settings().extract_confidence_threshold)

    events = [writer.event(d) for d in parsed.events]
    for op in parsed.operations:
        writer.operation(op, parsed.report_date or doc.report_date, events)
    for c in parsed.casing:
        writer.casing(c)
    for m in parsed.mud:
        writer.mud(m)

    doc.extract_status = "done"
    doc.extract_error = "; ".join(parsed.warnings)[:1000] or None
    doc.extracted_at = datetime.now(tz=UTC)
    session.flush()
    summary = {
        "document_id": doc.id,
        "status": "done",
        "events": len({e.id for e in events}),
        "merged": writer.merged,
        "operations": len(parsed.operations),
        "casing": len(parsed.casing),
        "mud": len(parsed.mud),
        "review_items": writer.reviews,
    }
    log.info("extracted document %s: %s", doc.id, summary)
    return summary


def _skip_reason(doc: Document) -> str | None:
    if doc.ingest_status not in ("processed", "needs_review"):
        return f"not ingested (status {doc.ingest_status})"
    if doc.doc_type not in EXTRACTABLE:
        return f"no extractor for document type {doc.doc_type}"
    if doc.well_id is None:
        return "well not identified; confirm the well name first"
    return None


def mark_failed(session: Session, document_id: int, message: str) -> None:
    doc = session.get(Document, document_id)
    if doc is not None:
        doc.extract_status = "failed"
        doc.extract_error = message[:1000]


# ─── Writing records ───────────────────────────────────────────────────────────────────────


def _pages(lines: list[Line]) -> int | None:
    return lines[0].page_no if lines else None


def _ids(lines: list[Line]) -> list[int]:
    seen: list[int] = []
    for ln in lines:
        if ln.span_id not in seen:
            seen.append(ln.span_id)
    return seen


class _Writer:
    def __init__(
        self,
        session: Session,
        doc: Document,
        ctx: WellContext,
        resolver: FormationResolver,
        threshold: float,
    ) -> None:
        self.s = session
        self.doc = doc
        self.ctx = ctx
        self.resolver = resolver
        self.threshold = threshold
        self.merged = 0
        self.reviews = 0

    # Events ------------------------------------------------------------------------------

    def event(self, d: EventDraft) -> Event:
        fm_id = self._formation(d)
        confidence = d.penalties.apply(ocr_confidence(d.primary))
        EXTRACTION_CONFIDENCE.labels(kind="event").observe(confidence)
        tvd, tvdss = self.ctx.depth_refs(d.md_m)
        existing = self._match(d)
        if existing is not None:
            self.merged += 1
            ev = existing
            ev.subtype = ev.subtype or d.subtype
            ev.md_m = ev.md_m if ev.md_m is not None else d.md_m
            if ev.tvd_m is None and tvd is not None:
                ev.tvd_m, ev.tvdss_m = tvd, tvdss
            ev.formation_id = ev.formation_id or fm_id
            ev.event_date = ev.event_date or d.event_date
            ev.t_start = ev.t_start or d.t_start
            ev.t_end = ev.t_end or d.t_end
            ev.hole_size_in = ev.hole_size_in or d.hole_size_in
            ev.mw_sg = ev.mw_sg or d.mw_sg
            ev.params = {**d.params, **(ev.params or {})}
            if ev.npt_hours is None or (d.npt_stated and len(d.mitigations) > len(ev.mitigations)):
                ev.npt_hours = d.npt_hours
            ev.cause_text = ev.cause_text or d.cause_text
            ev.confidence = max(ev.confidence, confidence)  # corroborated by another report
        else:
            ev = Event(
                well_id=self.ctx.well_id,
                wellbore_id=self.ctx.wellbore_id if self.ctx.single_wellbore else None,
                event_type=d.event_type,
                subtype=d.subtype,
                severity=d.severity,
                t_start=d.t_start,
                t_end=d.t_end,
                event_date=d.event_date,
                md_m=_r(d.md_m),
                tvd_m=tvd,
                tvdss_m=tvdss,
                formation_id=fm_id,
                hole_size_in=d.hole_size_in,
                mw_sg=_r(d.mw_sg, 3),
                params=d.params,
                cause_text=d.cause_text,
                description=d.description,
                npt_hours=d.npt_hours,
                confidence=confidence,
                source="rules",
                status="active",
            )
            self.s.add(ev)
            self.s.flush()
        self._evidence(ev, d)
        self._mitigations(ev, d)
        ev.resolved = _resolved(ev)
        self.s.flush()
        if confidence < self.threshold:
            self._review(
                "event",
                ev.id,
                d.primary,
                confidence,
                d.penalties.reasons or ["low text-recognition confidence"],
                _event_proposal(ev),
            )
        return ev

    def _formation(self, d: EventDraft) -> int | None:
        stated = self.resolver.find(d.formation_text)
        header = self.resolver.find(d.header_formation)
        at_md = self.ctx.formation_at(d.md_m)
        if stated is not None:
            if at_md is not None and stated != at_md:
                d.penalties.add("formation named in the report differs from the well tops", 0.1)
            return stated
        if header is not None:
            return header
        if at_md is not None:
            d.penalties.add("formation not named; taken from the well's formation tops", 0.05)
            return at_md
        d.penalties.add("formation unknown", 0.1)
        return None

    def _match(self, d: EventDraft) -> Event | None:
        if d.md_m is None:
            return None
        q = select(Event).where(
            Event.well_id == self.ctx.well_id,
            Event.event_type == d.event_type,
            Event.status == "active",
            Event.md_m.between(d.md_m - MERGE_DEPTH_M, d.md_m + MERGE_DEPTH_M),
        )
        if d.event_date is not None:
            q = q.where(
                (Event.event_date.is_(None))
                | Event.event_date.between(
                    d.event_date - timedelta(days=MERGE_DAYS),
                    d.event_date + timedelta(days=MERGE_DAYS),
                )
            )
        candidates = list(self.s.scalars(q))
        if not candidates:
            return None
        return min(candidates, key=lambda e: abs((e.md_m or 0) - (d.md_m or 0)))

    def _evidence(self, ev: Event, d: EventDraft) -> None:
        have = {e.span_id for e in ev.evidence}
        for role, lines in (("primary", d.primary), ("supporting", d.supporting)):
            for ln in lines:
                if ln.span_id in have:
                    continue
                have.add(ln.span_id)
                ev.evidence.append(
                    EventEvidence(
                        span_id=ln.span_id, document_id=self.doc.id, page_no=ln.page_no, role=role
                    )
                )

    def _mitigations(self, ev: Event, d: EventDraft) -> None:
        have = {m.action_code for m in ev.mitigations}
        seq = max((m.seq for m in ev.mitigations), default=0)
        added: list[tuple[Mitigation, MitigationDraft]] = []
        for md in d.mitigations:
            if md.action_code in have and md.action_code != "OTHER":
                continue  # the same action told again by another report
            seq += 1
            mit = self._mitigation(ev, md, seq)
            ev.mitigations.append(mit)
            added.append((mit, md))
            have.add(md.action_code)
        self.s.flush()
        for mit, md in added:
            EXTRACTION_CONFIDENCE.labels(kind="mitigation").observe(mit.confidence)
            if mit.confidence < self.threshold:
                self._review(
                    "mitigation",
                    mit.id,
                    md.lines,
                    mit.confidence,
                    md.penalties.reasons or ["low text-recognition confidence"],
                    {
                        "action_code": mit.action_code,
                        "action_text": mit.action_text,
                        "outcome": mit.outcome,
                        "npt_hours_after": mit.npt_hours_after,
                    },
                )

    def _mitigation(self, ev: Event, md: MitigationDraft, seq: int) -> Mitigation:
        code = md.action_code if md.action_code in ACTION_CODES else "OTHER"
        return Mitigation(
            event_id=ev.id,
            seq=seq,
            action_code=code,
            action_text=md.action_text,
            t_start=md.t_start,
            outcome=md.outcome,
            npt_hours_after=_r(md.npt_hours, 2),
            document_id=self.doc.id,
            page_no=_pages(md.lines),
            span_ids=_ids(md.lines),
            confidence=md.penalties.apply(ocr_confidence(md.lines)),
        )

    # DDR lines ---------------------------------------------------------------------------

    def operation(self, op: Any, report_date: date | None, events: list[Event]) -> None:
        if self.ctx.wellbore_id is None:
            return
        self.s.add(
            DdrOperation(
                wellbore_id=self.ctx.wellbore_id,
                document_id=self.doc.id,
                page_no=_pages(op.lines),
                report_date=report_date,
                t_from=op.t_from,
                t_to=op.t_to,
                hours=op.hours,
                md_m=_r(op.md_m),
                activity_code=op.code[:40],
                phase=ddr.phase(op.code),
                description=op.description,
                is_npt=op.code.startswith("NPT"),
                npt_category=ddr.npt_category(op.code),
                event_id=events[op.event_index].id if op.event_index is not None else None,
                span_ids=_ids(op.lines),
            )
        )

    # Casing, cement, mud -----------------------------------------------------------------

    def casing(self, c: CasingDraft) -> None:
        if self.ctx.wellbore_id is None:
            return
        if c.shoe_md_m is not None and self.s.scalar(
            select(func.count()).where(
                CasingString.wellbore_id == self.ctx.wellbore_id,
                CasingString.od_in == c.od_in,
                CasingString.shoe_md_m.between(c.shoe_md_m - 5, c.shoe_md_m + 5),
            )
        ):
            return  # already known from another report
        confidence = c.penalties.apply(ocr_confidence(c.lines))
        EXTRACTION_CONFIDENCE.labels(kind="casing").observe(confidence)
        tvd, tvdss = self.ctx.depth_refs(c.shoe_md_m)
        _, toc_tvdss = self.ctx.depth_refs(c.toc_md_m)
        row = CasingString(
            wellbore_id=self.ctx.wellbore_id,
            od_in=c.od_in,
            hole_size_in=c.hole_size_in,
            shoe_md_m=_r(c.shoe_md_m),
            shoe_tvd_m=tvd,
            shoe_tvdss_m=tvdss,
            document_id=self.doc.id,
            page_no=_pages(c.lines),
            span_ids=_ids(c.lines),
            confidence=confidence,
        )
        row.cement_jobs = [
            CementJob(
                toc_md_m=_r(c.toc_md_m),
                toc_tvdss_m=toc_tvdss,
                returns=c.returns,
                document_id=self.doc.id,
                page_no=_pages(c.lines),
                span_ids=_ids(c.lines),
                confidence=confidence,
            )
        ]
        self.s.add(row)
        self.s.flush()
        if confidence < self.threshold:
            self._review(
                "casing",
                row.id,
                c.lines,
                confidence,
                c.penalties.reasons,
                {
                    "od_in": c.od_in,
                    "hole_size_in": c.hole_size_in,
                    "shoe_md_m": _r(c.shoe_md_m),
                    "toc_md_m": _r(c.toc_md_m),
                    "returns": c.returns,
                },
            )

    def mud(self, m: MudDraft) -> None:
        if self.ctx.wellbore_id is None:
            return
        if self.s.scalar(
            select(func.count()).where(
                MudInterval.wellbore_id == self.ctx.wellbore_id,
                MudInterval.md_from_m.between(m.md_from_m - 5, m.md_from_m + 5),
                MudInterval.md_to_m.between(m.md_to_m - 5, m.md_to_m + 5),
            )
        ):
            return
        confidence = m.penalties.apply(ocr_confidence(m.lines))
        EXTRACTION_CONFIDENCE.labels(kind="mud").observe(confidence)
        row = MudInterval(
            wellbore_id=self.ctx.wellbore_id,
            md_from_m=_r(m.md_from_m) or 0.0,
            md_to_m=_r(m.md_to_m) or 0.0,
            tvdss_from_m=self.ctx.depth_refs(m.md_from_m)[1],
            tvdss_to_m=self.ctx.depth_refs(m.md_to_m)[1],
            hole_size_in=m.hole_size_in,
            mud_type=(m.mud_type or "")[:40] or None,
            mw_sg=_r(m.mw_sg, 3),
            document_id=self.doc.id,
            page_no=_pages(m.lines),
            span_ids=_ids(m.lines),
            confidence=confidence,
        )
        self.s.add(row)
        self.s.flush()
        if confidence < self.threshold:
            self._review(
                "mud",
                row.id,
                m.lines,
                confidence,
                m.penalties.reasons,
                {
                    "md_from_m": row.md_from_m,
                    "md_to_m": row.md_to_m,
                    "hole_size_in": m.hole_size_in,
                    "mud_type": row.mud_type,
                    "mw_sg": row.mw_sg,
                },
            )

    # Review queue ------------------------------------------------------------------------

    def _review(
        self,
        kind: str,
        target_id: int,
        lines: list[Line],
        confidence: float,
        reasons: list[str],
        proposed: dict[str, Any],
    ) -> None:
        self.reviews += 1
        self.s.add(
            ReviewItem(
                kind=kind,
                target_id=target_id,
                document_id=self.doc.id,
                page_no=_pages(lines),
                span_ids=_ids(lines),
                reason="; ".join(reasons) or "low confidence",
                confidence=confidence,
                proposed=proposed,
                status="pending",
            )
        )


def _r(v: float | None, nd: int = 1) -> float | None:
    return None if v is None else round(float(v), nd)


def _resolved(ev: Event) -> bool | None:
    outcomes = [m.outcome for m in ev.mitigations]
    if "success" in outcomes:
        return True
    if outcomes and all(o == "fail" for o in outcomes):
        return False
    return None


def _event_proposal(ev: Event) -> dict[str, Any]:
    return {
        "event_type": ev.event_type,
        "subtype": ev.subtype,
        "severity": ev.severity,
        "md_m": ev.md_m,
        "formation_id": ev.formation_id,
        "event_date": ev.event_date.isoformat() if ev.event_date else None,
        "npt_hours": ev.npt_hours,
        "params": ev.params,
    }


def pending_documents(session: Session, only_failed: bool = False) -> list[int]:
    statuses = ("failed",) if only_failed else ("pending", "failed")
    return list(
        session.scalars(
            select(Document.id)
            .where(
                Document.extract_status.in_(statuses),
                Document.ingest_status.in_(("processed", "needs_review")),
            )
            .order_by(Document.id)
        )
    )


def reset_status(session: Session, document_ids: list[int]) -> None:
    session.execute(
        update(Document)
        .where(Document.id.in_(document_ids))
        .values(extract_status="pending", extract_error=None)
    )
