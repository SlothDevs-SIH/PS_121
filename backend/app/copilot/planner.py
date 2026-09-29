"""Rule-based planner: which read-only tools answer a question, with which arguments.

Deterministic, offline and testable: it reads well names (and aliases), formations (and
synonyms), problem types, hole size, radius and an alert id from the question, then picks
the tools by intent. An LLM agent (``app.copilot.llm``) can replace it when a model is
configured; the tools and the citation rules stay the same.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Formation, Well

EVENT_WORDS: list[tuple[str, str]] = [
    (r"lost circulation|lost returns|mud loss|\blosses\b|\bloss\b|losing (?:mud|returns)", "LOSS"),
    (r"\bkicks?\b|\binflux\b|well control", "KICK"),
    (r"stuck pipe|\bstuck\b|differential sticking", "STUCK"),
    (r"tight (?:hole|spot)s?|\boverpull", "TIGHT"),
    (r"\btorque\b", "TORQUE"),
    (r"instabilit|cavings|sloughing", "INSTAB"),
    (r"\bball(?:ing|ed)\b", "BALLING"),
    (r"over-?pressure|abnormal pressure", "OVERP"),
    (r"gas (?:show|peak|influx|cut)|connection gas", "GAS"),
    (r"\bcement(?:ing)?\b", "CEMENT"),
]
DOMAIN = re.compile(
    r"drill|\bwells?\b|\bmud\b|casing|cement|formation|\bbit\b|\bhole\b|\bloss|kick|stuck|"
    r"torque|\brig\b|depth|report|\bddr\b|\bwcr\b|\bnpt\b|pipe|alert|offset|risk|ledger|"
    r"treatment|lcm|pill|tipam|barail|girujan|namsang|kopili|sylhet|langpar|dhekiajuli|"
    r"handover|shift|tight|balling|pressure|section|lesson|problem|event|trajectory",
    re.I,
)
OFF_TOPIC = re.compile(
    r"\b(?:oil price|stock|share price|weather|salary|election|cricket|football|recipe|"
    r"poem|joke|capital of)\b",
    re.I,
)
UNKNOWN_WELL = re.compile(r"\b[A-Z]{2,5}-[A-Z]{2,5}-[A-Z0-9]{1,4}\b")
HOLE = re.compile(
    r"\b(26|17|16|12|9|8|6)\s*(?:(?:-|\s)?(?:1/2|½|1/4|¼|3/4|¾|\.5|\.25|\.75))?\s*(?:\"|″|in\b|inch)",
    re.I,
)
FRACTIONS = {
    "1/2": 0.5,
    "½": 0.5,
    "1/4": 0.25,
    "¼": 0.25,
    "3/4": 0.75,
    "¾": 0.75,
    ".5": 0.5,
    ".25": 0.25,
    ".75": 0.75,
}
RADIUS = re.compile(r"within\s+(\d+(?:\.\d+)?)\s*(?:km|kilomet)", re.I)
ALERT_ID = re.compile(r"\balert\s*#?\s*(\d+)\b", re.I)


@dataclass
class Entities:
    wells: list[tuple[int, str]] = field(default_factory=list)
    unknown_wells: list[str] = field(default_factory=list)
    formation: str | None = None
    event_type: str | None = None
    hole_size_in: float | None = None
    radius_km: float | None = None
    alert_id: int | None = None


@dataclass
class Plan:
    intent: str
    calls: list[tuple[str, dict[str, Any]]]
    entities: Entities
    refusal: str | None = None  # set when the question cannot be answered from the records
    question: str = ""


Vocab = tuple[
    dict[str, tuple[int, str]], dict[str, str]
]  # wells (name/alias → id, name), formations


def vocab(session: Session) -> Vocab:
    wells: dict[str, tuple[int, str]] = {}
    for wid, name, aliases in session.execute(select(Well.id, Well.canonical_name, Well.aliases)):
        for n in [name, *(aliases or [])]:
            wells[n.lower()] = (wid, name)
    fms: dict[str, str] = {}
    for name, syns in session.execute(select(Formation.name, Formation.synonyms)):
        for n in [name, *(syns or [])]:
            fms[n.lower()] = name
    return wells, fms


def _hole(text: str) -> float | None:
    m = HOLE.search(text)
    if not m:
        return None
    frac = next((v for k, v in FRACTIONS.items() if k in m.group(0)), 0.0)
    return float(m.group(1)) + frac


def extract(question: str, voc: Vocab) -> Entities:
    q = question.lower()
    wells, fms = voc
    ent = Entities()
    seen: set[int] = set()
    for key in sorted(wells, key=len, reverse=True):  # longest first: "syn-asm-41" before "41"
        if len(key) >= 5 and re.search(rf"(?<![\w-]){re.escape(key)}(?![\w-])", q):
            wid, name = wells[key]
            if wid not in seen:
                seen.add(wid)
                ent.wells.append((wid, name))
    known = {n.lower() for _, n in ent.wells} | set(wells)
    ent.unknown_wells = [w for w in UNKNOWN_WELL.findall(question) if w.lower() not in known]
    for key in sorted(fms, key=len, reverse=True):
        if re.search(rf"\b{re.escape(key)}\b", q):
            ent.formation = fms[key]
            break
    for pat, et in EVENT_WORDS:
        if re.search(pat, q):
            ent.event_type = et
            break
    ent.hole_size_in = _hole(question)
    if m := RADIUS.search(question):
        ent.radius_km = float(m.group(1))
    if m := ALERT_ID.search(question):
        ent.alert_id = int(m.group(1))
    return ent


def plan(
    session: Session,
    question: str,
    well_id: int | None = None,
    alert_id: int | None = None,
) -> Plan:
    return decide(question, vocab(session), well_id, alert_id)


def decide(
    question: str,
    voc: Vocab,
    well_id: int | None = None,
    alert_id: int | None = None,
) -> Plan:
    p = _decide(question, voc, well_id, alert_id)
    p.question = question
    return p


def _decide(
    question: str,
    voc: Vocab,
    well_id: int | None,
    alert_id: int | None,
) -> Plan:
    """Tools for ``question``; ``well_id`` / ``alert_id`` are the screen's context (the well
    or alert the user is looking at), used when the question says "this well" / "this alert"."""
    q = question.lower()
    ent = extract(question, voc)
    if ent.alert_id is None and alert_id is not None and "alert" in q:
        ent.alert_id = alert_id
    wid = ent.wells[0][0] if ent.wells else None
    if (
        wid is None
        and well_id is not None
        and re.search(r"this well|here|current|next|ahead|handover|shift", q)
    ):
        wid = well_id
    if ent.unknown_wells and not ent.wells:
        names = ", ".join(ent.unknown_wells)
        return Plan("refuse", [], ent, f"No record found: no well named {names} in the records.")
    if OFF_TOPIC.search(question) or not (DOMAIN.search(question) or ent.wells or ent.formation):
        return Plan("refuse", [], ent, "I can only answer from SMRITI's drilling records.")
    et, fm, r = ent.event_type, ent.formation, ent.radius_km

    if ent.alert_id is not None or re.search(r"why did (?:this|the) alert", q):
        if ent.alert_id is None:
            return Plan("refuse", [], ent, "Open the alert first, or give its number.")
        return Plan("alert", [("explain_alert", {"alert_id": ent.alert_id})], ent)

    if re.search(r"handover|shift note|next shift", q):
        if wid is None:
            return Plan("refuse", [], ent, "Which well? Name it, or ask from the well's screen.")
        calls: list[tuple[str, dict[str, Any]]] = [
            ("get_well_summary", {"well_id": wid}),
            ("get_risk_profile", {"well_id": wid}),
            ("get_events", {"well_id": wid, "radius_km": r or 5.0, "event_type": et}),
        ]
        return Plan("handover", calls, ent)

    if et and re.search(
        r"what worked|which (?:treatment|action|remed)|best (?:action|treatment|way|option)|"
        r"success rate|effective|mitigat|"
        r"how (?:do|did|to|should) .*(?:cure|treat|stop|fix|free|control)|\bcure\b|\bremed",
        q,
    ):
        return Plan("ledger", [("get_ledger", {"event_type": et, "formation": fm})], ent)

    if wid is not None and re.search(r"\brisk|likely|chance|probab|expect|hazard|ahead", q):
        return Plan("risk", [("get_risk_profile", {"well_id": wid})], ent)

    asks_events = et or re.search(r"problems?|events?|incidents?|\bnpt\b|which wells|how many", q)
    offsets = re.search(r"offset|nearby|near |neighbo|around", q)
    if wid is not None and offsets and not asks_events:
        return Plan("offsets", [("get_offset_wells", {"well_id": wid, "radius_km": r or 5.0})], ent)

    if asks_events and (et or fm or wid is not None or ent.hole_size_in):
        if wid is not None and offsets and r is None:
            r = 5.0  # "offset wells" without a radius: the default offset radius
        filters = {"formation": fm, "well_id": wid, "radius_km": r, "event_type": et}
        calls = [("get_events", {**filters, "hole_size_in": ent.hole_size_in})]
        if re.search(r"what .*(?:use|did|done|action)|how (?:was|were)|kill", q):
            calls.append(("search_documents", {**filters, "query": question}))
        return Plan("events", calls, ent)

    if wid is not None and re.search(
        r"summar|tell me about|overview|status of|what is|describe", q
    ):
        return Plan("well", [("get_well_summary", {"well_id": wid})], ent)

    return Plan(
        "search",
        [
            (
                "search_documents",
                {
                    "query": question,
                    "well_id": wid,
                    "radius_km": r,
                    "formation": fm,
                    "event_type": et,
                },
            )
        ],
        ent,
    )
