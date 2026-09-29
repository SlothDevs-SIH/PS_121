"""Review queue (S2): list low-confidence extractions and apply a reviewer's decision.

accept   the proposed values are right: the target record becomes verified.
correct  some values are replaced (validated per kind), derived values are recomputed and
         the record becomes verified; the (proposed, correction) pair is kept on the item,
         which is what the evaluation gold set is built from.
reject   not a real fact: events become status 'rejected' (kept, hidden); other records
         are deleted (the item keeps what was proposed, for the audit trail).
"""

from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError
from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from app.api.v1.params import ConflictError, InvalidParamsError, decode_cursor, encode_cursor
from app.api.v1.schemas.events import EventParamsIn
from app.api.v1.schemas.review import (
    ReviewAccept,
    ReviewCorrect,
    ReviewItem,
    ReviewPage,
    ReviewReject,
)
from app.core.errors import NotFoundError
from app.db.models import (
    CasingString,
    CementJob,
    Document,
    Event,
    Formation,
    Mitigation,
    MudInterval,
    Well,
)
from app.db.models import ReviewItem as ReviewRow
from app.db.vocab import (
    REVIEW_STATUSES,
    ActionCode,
    CementReturns,
    EventType,
    MitigationOutcome,
    Severity,
)
from app.extract.evidence import record_evidence
from app.extract.service import WellContext
from app.search.service import refresh_lesson_cards


def _items(session: Session, rows: list[ReviewRow]) -> list[ReviewItem]:
    doc_ids = {r.document_id for r in rows if r.document_id is not None}
    docs = {
        d.id: d
        for d in (
            session.scalars(select(Document).where(Document.id.in_(doc_ids))) if doc_ids else []
        )
    }
    well_ids = {d.well_id for d in docs.values() if d.well_id is not None}
    wells = (
        dict(
            session.execute(select(Well.id, Well.canonical_name).where(Well.id.in_(well_ids)))
            .tuples()
            .all()
        )
        if well_ids
        else {}
    )
    evidence = record_evidence(session, [(r.document_id, r.page_no, r.span_ids) for r in rows])
    out = []
    for r, refs in zip(rows, evidence, strict=True):
        d = docs.get(r.document_id) if r.document_id is not None else None
        out.append(
            ReviewItem(
                id=r.id,
                kind=r.kind,
                target_id=r.target_id,
                document_id=r.document_id,
                filename=d.filename if d else None,
                doc_type=d.doc_type if d else None,
                well_id=d.well_id if d else None,
                well_name=wells.get(d.well_id) if d and d.well_id else None,
                page_no=r.page_no,
                span_ids=list(r.span_ids or []),
                evidence=refs,
                field=r.field,
                reason=r.reason,
                confidence=r.confidence,
                proposed=r.proposed or {},
                status=r.status,
                decided_by=r.decided_by,
                decided_at=r.decided_at,
                correction=r.correction,
                created_at=r.created_at,
            )
        )
    return out


def list_items(
    session: Session,
    *,
    status: str | None,
    kind: str | None,
    document_id: int | None,
    limit: int,
    cursor: str | None,
) -> ReviewPage:
    after = decode_cursor(cursor, 2)
    q = select(ReviewRow)
    if status is not None:
        q = q.where(ReviewRow.status == status)
    if kind is not None:
        q = q.where(ReviewRow.kind == kind)
    if document_id is not None:
        q = q.where(ReviewRow.document_id == document_id)
    if after is not None:
        q = q.where(tuple_(ReviewRow.confidence, ReviewRow.id) > tuple_(*after))
    rows = list(session.scalars(q.order_by(ReviewRow.confidence, ReviewRow.id).limit(limit + 1)))
    page = rows[:limit]
    counts = {s: 0 for s in REVIEW_STATUSES}
    for s, n in session.execute(select(ReviewRow.status, func.count()).group_by(ReviewRow.status)):
        counts[str(s)] = int(n)
    return ReviewPage(
        items=_items(session, page),
        next_cursor=encode_cursor([page[-1].confidence, page[-1].id])
        if len(rows) > limit
        else None,
        status_counts=counts,
    )


# ─── Corrections: what a reviewer may change, per kind ─────────────────────────────────────


class _EventFix(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: EventType | None = None
    subtype: str | None = Field(default=None, max_length=40)
    severity: Severity | None = None
    md_m: float | None = Field(default=None, ge=0, le=15000)
    formation_id: int | None = None
    event_date: date | None = None
    npt_hours: float | None = Field(default=None, ge=0)
    params: EventParamsIn | None = None


class _MitigationFix(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_code: ActionCode | None = None
    action_text: str | None = Field(default=None, max_length=2000)
    outcome: MitigationOutcome | None = None
    npt_hours_after: float | None = Field(default=None, ge=0)


class _CasingFix(BaseModel):
    model_config = ConfigDict(extra="forbid")
    od_in: float | None = Field(default=None, gt=0, le=40)
    hole_size_in: float | None = Field(default=None, gt=0, le=40)
    shoe_md_m: float | None = Field(default=None, ge=0, le=15000)
    toc_md_m: float | None = Field(default=None, ge=0, le=15000)
    returns: CementReturns | None = None


class _MudFix(BaseModel):
    model_config = ConfigDict(extra="forbid")
    md_from_m: float | None = Field(default=None, ge=0, le=15000)
    md_to_m: float | None = Field(default=None, ge=0, le=15000)
    hole_size_in: float | None = Field(default=None, gt=0, le=40)
    mud_type: str | None = Field(default=None, max_length=40)
    mw_sg: float | None = Field(default=None, ge=0.8, le=2.6)


_FIXES: dict[str, type[BaseModel]] = {
    "event": _EventFix,
    "mitigation": _MitigationFix,
    "casing": _CasingFix,
    "cement": _CasingFix,
    "mud": _MudFix,
}


def _validated(kind: str, fields: dict[str, JsonValue]) -> dict[str, Any]:
    model = _FIXES.get(kind)
    if model is None:
        raise InvalidParamsError(
            "fields", f"{kind} items cannot be corrected here; accept or reject"
        )
    try:
        return model.model_validate(fields).model_dump(exclude_unset=True)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"])
        raise InvalidParamsError(f"fields.{loc}", first["msg"]) from exc


# ─── Decisions ─────────────────────────────────────────────────────────────────────────────


def decide(
    session: Session,
    item_id: int,
    decision: ReviewAccept | ReviewCorrect | ReviewReject,
    user: str,
) -> ReviewItem:
    item = session.get(ReviewRow, item_id)
    if item is None:
        raise NotFoundError(f"Review item {item_id} not found.", {"item_id": item_id})
    if item.status != "pending":
        raise ConflictError(
            f"Review item {item_id} was already {item.status}.",
            {"status": item.status, "decided_by": item.decided_by},
        )
    now = datetime.now(tz=UTC)
    if isinstance(decision, ReviewAccept):
        _apply(session, item, {}, user, now)
        item.status = "accepted"
        item.correction = {"note": decision.note} if decision.note else None
    elif isinstance(decision, ReviewCorrect):
        fix = _validated(item.kind, decision.fields)
        _apply(session, item, fix, user, now)
        item.status = "corrected"
        item.correction = {**decision.fields, **({"note": decision.note} if decision.note else {})}
    else:
        _reject(session, item, user, now)
        item.status = "rejected"
        item.correction = {"reason": decision.reason}
    item.decided_by, item.decided_at = user, now
    session.flush()
    return _items(session, [item])[0]


def _target(session: Session, item: ReviewRow) -> Any:
    model = {
        "event": Event,
        "mitigation": Mitigation,
        "casing": CasingString,
        "cement": CementJob,
        "mud": MudInterval,
    }.get(item.kind)
    if model is None or item.target_id is None:
        return None
    return session.get(model, item.target_id)


def _apply(
    session: Session, item: ReviewRow, fix: dict[str, Any], user: str, now: datetime
) -> None:
    target = _target(session, item)
    if target is None:
        if fix:
            raise ConflictError("The record under review no longer exists.", {"kind": item.kind})
        return
    if isinstance(target, Event):
        _fix_event(session, target, fix)
        target.verified, target.verified_by, target.verified_at = True, user, now
        refresh_lesson_cards(session, [target.id])
    elif isinstance(target, Mitigation):
        for k, v in fix.items():
            setattr(target, k, v)
        target.verified = True
        event = session.get(Event, target.event_id)
        if event is not None:
            outcomes = [m.outcome for m in event.mitigations]
            event.resolved = (
                True
                if "success" in outcomes
                else (False if outcomes and set(outcomes) == {"fail"} else None)
            )
            refresh_lesson_cards(session, [event.id])
    elif isinstance(target, CasingString | CementJob):
        casing = target if isinstance(target, CasingString) else target.casing
        _fix_casing(session, casing, fix)
        casing.verified = True
        for job in casing.cement_jobs:
            job.verified = True
    elif isinstance(target, MudInterval):
        for k, v in fix.items():
            setattr(target, k, v)
        if target.md_to_m <= target.md_from_m:
            raise InvalidParamsError("fields.md_to_m", "md_to_m must be deeper than md_from_m")
        ctx = _ctx_for_wellbore(session, target.wellbore_id)
        target.tvdss_from_m = ctx.depth_refs(target.md_from_m)[1]
        target.tvdss_to_m = ctx.depth_refs(target.md_to_m)[1]
        target.verified = True


def _ctx_for_wellbore(session: Session, wellbore_id: int) -> WellContext:
    from app.db.models import Wellbore

    wb = session.get(Wellbore, wellbore_id)
    assert wb is not None
    return WellContext.load(session, wb.well_id)


def _fix_event(session: Session, ev: Event, fix: dict[str, Any]) -> None:
    fid = fix.get("formation_id")
    if fid is not None and session.get(Formation, fid) is None:
        raise InvalidParamsError("fields.formation_id", "unknown formation")
    params = fix.pop("params", None)
    for k, v in fix.items():
        setattr(ev, k, v)
    if params is not None:
        ev.params = {**(ev.params or {}), **{k: v for k, v in params.items() if v is not None}}
    if "md_m" in fix:
        ctx = WellContext.load(session, ev.well_id)
        ev.tvd_m, ev.tvdss_m = ctx.depth_refs(ev.md_m)
        if "formation_id" not in fix:
            ev.formation_id = ctx.formation_at(ev.md_m) or ev.formation_id


def _fix_casing(session: Session, casing: CasingString, fix: dict[str, Any]) -> None:
    ctx = _ctx_for_wellbore(session, casing.wellbore_id)
    for k in ("od_in", "hole_size_in", "shoe_md_m"):
        if k in fix:
            setattr(casing, k, fix[k])
    if casing.od_in and casing.hole_size_in and casing.od_in >= casing.hole_size_in:
        raise InvalidParamsError("fields.od_in", "casing must be smaller than its hole")
    casing.shoe_tvd_m, casing.shoe_tvdss_m = ctx.depth_refs(casing.shoe_md_m)
    if casing.cement_jobs and ("toc_md_m" in fix or "returns" in fix):
        job = casing.cement_jobs[0]
        if "toc_md_m" in fix:
            job.toc_md_m = fix["toc_md_m"]
            job.toc_tvdss_m = ctx.depth_refs(job.toc_md_m)[1]
        if "returns" in fix:
            job.returns = fix["returns"]


def _reject(session: Session, item: ReviewRow, user: str, now: datetime) -> None:
    target = _target(session, item)
    if target is None:
        return
    if isinstance(target, Event):
        target.status = "rejected"
        target.verified, target.verified_by, target.verified_at = False, user, now
        return
    event_id = target.event_id if isinstance(target, Mitigation) else None
    session.delete(target)
    session.flush()
    if event_id is not None:
        refresh_lesson_cards(session, [event_id])
