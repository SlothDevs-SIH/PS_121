"""The copilot's fixed, read-only tools (master plan §Stage 10).

Each tool calls a service function (never SQL written from the question), checks the
user's permission, and returns facts with their **citations**: a report page (document,
page, highlighted spans) or a database record (event, well, alert). The answer composer
may only state what a tool returned, each sentence tied to a citation.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.api.v1.schemas.common import EvidenceRef
from app.core.auth import CurrentUser
from app.search.hybrid import SearchQuery
from app.search.hybrid import run as search_run

EVENT_LABELS = {
    "LOSS": "losses",
    "KICK": "kick",
    "GAS": "gas",
    "OVERP": "overpressure",
    "STUCK": "stuck pipe",
    "TIGHT": "tight hole",
    "TORQUE": "high torque",
    "INSTAB": "hole instability",
    "BALLING": "bit balling",
    "FISH": "fishing",
    "CEMENT": "cementing problems",
    "CASING": "casing problems",
    "EQUIP": "equipment failure",
    "WAIT": "waiting",
    "OTHER_NPT": "other NPT",
}
PLURAL = {"KICK": "kicks", "FISH": "fishing jobs", "EQUIP": "equipment failures"}


def plural(event_type: str | None) -> str:
    """Label for a count of events: 'kicks', 'losses', 'stuck pipe'…"""
    if not event_type:
        return "drilling problems"
    return PLURAL.get(event_type, EVENT_LABELS.get(event_type, event_type))


@dataclass
class Citation:
    """What a sentence rests on. ``kind`` page: a report page; record: a database row."""

    kind: str  # page | record
    label: str
    document_id: int | None = None
    page_no: int | None = None
    span_ids: list[int] = field(default_factory=list)
    filename: str | None = None
    record_type: str | None = None  # event | well | alert | ledger | risk
    record_id: int | None = None
    text: str | None = None  # the cited text itself (page snippet), for faithfulness checks

    @classmethod
    def page(cls, ref: EvidenceRef, text: str | None = None) -> "Citation":
        return cls(
            "page",
            f"{ref.doc_type or 'report'} p.{ref.page_no}",
            document_id=ref.document_id,
            page_no=ref.page_no,
            span_ids=list(ref.span_ids),
            filename=ref.filename,
            text=text,
        )

    @classmethod
    def record(cls, record_type: str, record_id: int, label: str) -> "Citation":
        return cls("record", label, record_type=record_type, record_id=record_id)

    def key(self) -> tuple[object, ...]:
        return (self.kind, self.document_id, self.page_no, self.record_type, self.record_id)


@dataclass
class Fact:
    """One sentence the answer may state, and what it rests on."""

    text: str
    citations: list[Citation]


@dataclass
class ToolResult:
    tool: str
    args: dict[str, Any]
    facts: list[Fact] = field(default_factory=list)
    empty_reason: str | None = None  # set when the tool found nothing
    denied: bool = False
    data: dict[str, Any] = field(default_factory=dict)  # structured output (LLM mode, UI)


@dataclass(frozen=True)
class Tool:
    name: str
    permission: str
    description: str
    params: dict[str, str]  # name -> JSON type ("string", "number", "integer")
    fn: Callable[..., ToolResult]


def _event_citations(ev: Any) -> list[Citation]:
    refs = [Citation.page(r) for r in ev.evidence[:2]]
    return refs or [Citation.record("event", ev.id, f"event {ev.id}")]


def _depth(md: float | None) -> str:
    return f"{md:,.0f} m MD" if md is not None else "an unrecorded depth"


# ─── Tools ──────────────────────────────────────────────────────────────────────


def search_documents(
    session: Session,
    query: str,
    well_id: int | None = None,
    radius_km: float | None = None,
    formation: str | None = None,
    event_type: str | None = None,
) -> ToolResult:
    sq = SearchQuery(
        q=query,
        well_id=well_id,
        radius_km=radius_km if well_id else None,
        formation=formation,
        event_types=(event_type,) if event_type else (),
        limit=5,
    )
    res = search_run(session, sq)
    out = ToolResult(
        "search_documents",
        {"query": query, "well_id": well_id, "radius_km": radius_km, "formation": formation},
        data={"passages": len(res.passages), "lessons": len(res.lessons)},
    )
    if res.no_record_found or (not res.passages and not res.lessons):
        out.empty_reason = "No record found in the indexed documents."
        return out
    for card in res.lessons[:3]:
        parts = [f"{card.well_name}: {card.problem}"]
        if card.action_taken:
            parts.append(f"Action: {card.action_taken}")
        if card.outcome:
            parts.append(f"Outcome: {card.outcome}")
        cites = [Citation.page(r) for r in card.evidence[:2]] or [
            Citation.record("event", card.event_id, f"event {card.event_id}")
        ]
        out.facts.append(Fact(". ".join(p.rstrip(".") for p in parts) + ".", cites))
    for p in res.passages[:3]:
        ref = EvidenceRef(
            document_id=p.document_id,
            page_no=p.page_from,
            span_ids=p.span_ids,
            filename=p.filename,
            doc_type=p.doc_type,
        )
        snippet = " ".join(p.snippet.split())
        short = snippet if len(snippet) <= 220 else snippet[:217].rsplit(" ", 1)[0] + "…"
        out.facts.append(
            Fact(
                f"{p.well_name or p.filename} report says: “{short}”", [Citation.page(ref, snippet)]
            )
        )
    out.data["top_pages"] = [(p.document_id, p.page_from) for p in res.passages[:5]]
    return out


def get_events(
    session: Session,
    event_type: str | None = None,
    formation: str | None = None,
    well_id: int | None = None,
    radius_km: float | None = None,
    hole_size_in: float | None = None,
    limit: int = 20,
) -> ToolResult:
    from app.extract.events_service import list_events

    page = list_events(
        session,
        event_types=[event_type] if event_type else None,
        formation=formation,
        well_id=well_id,
        radius_km=radius_km if well_id else None,
        tvdss_from_m=None,
        tvdss_to_m=None,
        date_from=None,
        date_to=None,
        verified=None,
        min_confidence=None,
        limit=200,
        cursor=None,
    )
    items = [
        e
        for e in page.items
        if hole_size_in is None
        or (e.hole_size_in is not None and abs(e.hole_size_in - hole_size_in) < 0.2)
    ]
    args = {
        "event_type": event_type,
        "formation": formation,
        "well_id": well_id,
        "radius_km": radius_km,
        "hole_size_in": hole_size_in,
    }
    out = ToolResult("get_events", args, data={"count": len(items)})
    if not items:
        what = plural(event_type) if event_type else "problems"
        where = f" in the {formation}" if formation else ""
        scope = " for this well and its offsets" if well_id and radius_km else ""
        scope = scope or (" for this well" if well_id else "")
        out.empty_reason = f"No recorded {what}{where}{scope}."
        if event_type and formation:  # say where this problem *was* recorded, as its own fact
            other = get_events(session, event_type=event_type, well_id=well_id, radius_km=radius_km)
            by_fm: dict[str, int] = other.data.get("formations", {})
            if other.facts and by_fm:
                listing = ", ".join(f"{k} ({v})" for k, v in sorted(by_fm.items()))
                out.facts.append(
                    Fact(
                        f"No recorded {what}{where}. {what.capitalize()} were recorded in: "
                        f"{listing}.",
                        other.facts[0].citations,
                    )
                )
        return out
    wells = sorted({e.well_name for e in items})
    what = plural(event_type)
    where = f" in the {formation}" if formation else ""
    npt = sum(e.npt_hours or 0 for e in items)
    out.facts.append(
        Fact(
            f"{len(items)} recorded {what}{where} in {len(wells)} well(s): {', '.join(wells)}"
            f" ({npt:.1f} h NPT in total).",
            [c for e in items[:6] for c in _event_citations(e)][:6],
        )
    )
    for e in sorted(items, key=lambda e: (e.well_name, e.md_m or 0))[: max(1, limit)][:8]:
        bits = [
            f"{e.well_name}: {EVENT_LABELS.get(e.event_type, e.event_type)} at {_depth(e.md_m)}"
        ]
        if e.formation:
            bits.append(f"in the {e.formation}")
        if e.event_date:
            bits.append(f"on {e.event_date.isoformat()}")
        if e.mw_sg is not None:
            bits.append(f"with mud weight {e.mw_sg:.2f} SG")
        if e.npt_hours:
            bits.append(f"({e.npt_hours:.1f} h NPT)")
        out.facts.append(Fact(" ".join(bits) + ".", _event_citations(e)))
    out.data["well_names"] = wells
    out.data["event_ids"] = [e.id for e in items]
    fms: dict[str, int] = {}
    for e in items:
        if e.formation:
            fms[e.formation] = fms.get(e.formation, 0) + 1
    out.data["formations"] = fms
    return out


def get_offset_wells(session: Session, well_id: int, radius_km: float = 5.0) -> ToolResult:
    from app.geo.service import surface_offsets
    from app.normalise.wells_service import get_well_or_404

    well = get_well_or_404(session, well_id)
    rows = [o for o in surface_offsets(session, well_id, radius_km * 1000) if o.status != "planned"]
    out = ToolResult(
        "get_offset_wells",
        {"well_id": well_id, "radius_km": radius_km},
        data={"well_names": [o.name for o in rows]},
    )
    if not rows:
        out.empty_reason = (
            f"No drilled offset well within {radius_km:g} km of {well.canonical_name}."
        )
        return out
    near = ", ".join(f"{o.name} ({o.distance_m:,.0f} m)" for o in rows[:8])
    more = f" and {len(rows) - 8} more" if len(rows) > 8 else ""
    out.facts.append(
        Fact(
            f"{len(rows)} drilled offset well(s) within {radius_km:g} km of {well.canonical_name}"
            f" (surface distance): {near}{more}.",
            [Citation.record("well", o.well_id, o.name) for o in rows[:6]],
        )
    )
    return out


def get_risk_profile(session: Session, well_id: int) -> ToolResult:
    from app.risk.prior import risk_profile

    p = risk_profile(session, well_id)
    out = ToolResult("get_risk_profile", {"well_id": well_id}, data={"intervals": len(p.intervals)})
    shown = 0
    for iv in p.intervals:
        top = [r for r in iv.risks if r.probability >= 0.15][:2]
        for r in top:
            prog = " (top prognosed from offsets)" if iv.prognosed else ""
            evs = [i for o in iv.offsets for i in o.events.get(r.event_type, [])][:3]
            cites = [Citation.record("event", i, f"event {i}") for i in evs] or [
                Citation.record("risk", well_id, f"{p.name} risk profile")
            ]
            out.facts.append(Fact(f"{iv.formation}{prog}: {r.label}.", cites))
            shown += 1
    if not shown:
        out.empty_reason = f"No problem reaches a 15% offset prior in any formation of {p.name}."
    return out


def get_ledger(session: Session, event_type: str, formation: str | None = None) -> ToolResult:
    from app.ledger.service import ledger

    try:
        led = ledger(session, event_type=event_type, formation=formation)
    except Exception:
        led = ledger(session, event_type=event_type)
        formation = None
    out = ToolResult(
        "get_ledger",
        {"event_type": event_type, "formation": formation},
        data={"ranked": [e.action_code for e in led.ranked]},
    )
    if not led.ranked:
        what = EVENT_LABELS.get(event_type, event_type)
        out.empty_reason = (
            f"Too few recorded outcomes to rank treatments for {what}"
            + (f" in the {formation}" if formation else "")
            + f" (fewer than {led.min_n} per action)."
        )
        return out
    for e in led.ranked[:3]:
        cites = [Citation.page(r) for c in e.cases[:2] for r in c.evidence[:1]] or [
            Citation.record("ledger", 0, "Mitigation Ledger")
        ]
        out.facts.append(Fact(e.summary + ".", cites))
    out.facts.append(Fact(led.caveat, []))  # the caveat is stated, not claimed
    return out


def get_well_summary(session: Session, well_id: int) -> ToolResult:
    from app.normalise.wells_service import well_detail

    w = well_detail(session, well_id)
    out = ToolResult("get_well_summary", {"well_id": well_id})
    rec = [Citation.record("well", w.id, w.name)]
    td = f", TD {w.td_md_m:,.0f} m MD" if w.td_md_m else ""
    kind = " ".join(x for x in (w.status, w.well_type) if x)
    out.facts.append(
        Fact(
            f"{w.name} is a {kind} well ({w.profile or 'unknown'} profile{td})"
            f" in {w.field}, spudded {w.spud_date or 'on an unrecorded date'}.",
            rec,
        )
    )
    counts = {k: v for k, v in w.event_counts.items() if v}
    if counts:
        listing = ", ".join(f"{v} {EVENT_LABELS.get(k, k)}" for k, v in sorted(counts.items()))
        out.facts.append(Fact(f"Recorded events: {listing}.", rec))
    for c in w.casing[:3]:
        if c.shoe_md_m is not None and c.od_in is not None:
            out.facts.append(
                Fact(
                    f'{c.od_in:g}" casing set at {c.shoe_md_m:,.0f} m MD.',
                    [Citation.page(r) for r in c.evidence[:1]] or rec,
                )
            )
    return out


def explain_alert(session: Session, alert_id: int) -> ToolResult:
    from app.alerts.service import get_alert

    a = get_alert(session, alert_id)
    out = ToolResult("explain_alert", {"alert_id": alert_id})
    rec = [Citation.record("alert", a.id, f"alert {a.id}")]
    kind = {
        "probability": "model probability",
        "similarity": "similarity (not a probability)",
        "prior": "offset prior",
        "indicator": "indicator value",
    }.get(a.score_kind, a.score_kind)
    out.facts.append(
        Fact(
            f"Alert {a.id} ({a.severity}, {a.status}) on {a.well_name}: {a.title}. Raised by "
            f"{', '.join(a.sources)} at {a.t_data:%Y-%m-%d %H:%M} (data time)"
            + (f", {kind} {a.score:.2f}" if a.score is not None else "")
            + ".",
            rec,
        )
    )
    out.facts.append(Fact(a.message, rec))
    for f in a.detail.get("fused", [])[:3]:
        out.facts.append(Fact(f"Also: {f['title']} ({f['source']}).", rec))
    if a.drivers:
        drv = ", ".join(f"{d.label} ({d.value} vs typical {d.typical})" for d in a.drivers[:3])
        out.facts.append(Fact(f"Top drivers: {drv}.", rec))
    for e in a.evidence:
        if e.kind != "stream" and e.refs:
            out.facts.append(
                Fact(
                    f"Past {EVENT_LABELS.get(e.event_type or '', 'event')} in {e.well_name}"
                    f" at {_depth(e.md_m)}.",
                    [Citation.page(r) for r in e.refs[:1]],
                )
            )
    for r in a.recommendations[:2]:
        out.facts.append(Fact(f"What worked before: {r.summary}.", rec))
    return out


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool(
            "search_documents",
            "read_knowledge",
            "Hybrid search over report pages and lesson cards",
            {
                "query": "string",
                "well_id": "integer",
                "radius_km": "number",
                "formation": "string",
                "event_type": "string",
            },
            search_documents,
        ),
        Tool(
            "get_events",
            "read_knowledge",
            "Recorded drilling problems, filtered by type, formation, well (+ radius), hole size",
            {
                "event_type": "string",
                "formation": "string",
                "well_id": "integer",
                "radius_km": "number",
                "hole_size_in": "number",
            },
            get_events,
        ),
        Tool(
            "get_offset_wells",
            "read_knowledge",
            "Drilled wells within a radius of a well (surface distance)",
            {"well_id": "integer", "radius_km": "number"},
            get_offset_wells,
        ),
        Tool(
            "get_risk_profile",
            "read_risk",
            "Offset prior probability of each problem in each formation of a well",
            {"well_id": "integer"},
            get_risk_profile,
        ),
        Tool(
            "get_ledger",
            "read_risk",
            "Treatments ranked by recorded success for a problem (optionally in a formation)",
            {"event_type": "string", "formation": "string"},
            get_ledger,
        ),
        Tool(
            "get_well_summary",
            "read_knowledge",
            "Facts about one well: status, profile, TD, events, casing",
            {"well_id": "integer"},
            get_well_summary,
        ),
        Tool(
            "explain_alert",
            "read_live",
            "Why an alert fired: sources, drivers, evidence, recommendations",
            {"alert_id": "integer"},
            explain_alert,
        ),
    )
}


def call(session: Session, user: CurrentUser, name: str, args: dict[str, Any]) -> ToolResult:
    tool = TOOLS[name]
    if not user.can(tool.permission):
        return ToolResult(
            name,
            args,
            denied=True,
            empty_reason=f"Your role does not allow {name.replace('_', ' ')} ({tool.permission}).",
        )
    clean = {k: v for k, v in args.items() if k in tool.params and v is not None}
    try:
        return tool.fn(session, **clean)
    except Exception as exc:  # a not-found well/alert becomes an honest "no record"
        msg = getattr(exc, "message", None) or str(exc)
        return ToolResult(name, clean, empty_reason=f"No record: {msg}")
