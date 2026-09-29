"""Well Completion Report parser: casing and cementing, mud programme, drilling problems.

The WCR summarises the whole well. Tables are read row by row with the unit taken from the
column header; a cell OCR could not read becomes null (and the row goes to review) rather
than a guess. Problem bullets ("- <date>: <problem>. Actions: <a> (<outcome>, <h> hrs); ...
NPT <h> hrs.") wrap over several lines and are re-joined before parsing, keeping the
mapping back to each line so every mitigation cites only its own spans.
"""

import re
from datetime import date

from app.extract import rules
from app.extract.drafts import (
    CasingDraft,
    EventDraft,
    Joined,
    Line,
    MitigationDraft,
    MudDraft,
    ParsedDocument,
)

_HEADING = re.compile(r"^\s*(\d{1,2})\s*[.,]\s*([A-Z][A-Z &/,\-]{3,})\s*$")
_UNITS_LINE = re.compile(r"Units\s*:\s*(metric|oilfield)", re.I)
_CASING_HEADER = re.compile(r"Shoe\s*MD\s*\(\s*(m|ft)\s*\)", re.I)
_MUD_HEADER = re.compile(r"Interval\s*\(\s*(m|ft)\s*\)", re.I)
_MUD_ROW = re.compile(
    r"^\s*([\d,]+)\s*[-\u2013\u2014]\s*([\d,]+)\s+(\S+)\s+(.+?)\s+(\d+(?:\.\d+)?\s*(?:SG|ppg))"
)
_BULLET = re.compile(r"^\s*[-\u2013\u2014~•*»]?\s*(\d{4})-(\d{2})-(\d{2})\s*[:;.]\s*(.*)$")
_ACTIONS = re.compile(r"\.\s+Actions?\s*[:;]\s*", re.I)
_TAIL_NPT = re.compile(r"\.?\s*NPT\s*[:=]?\s*(\d+(?:\.\d+)?)\s*hrs?\.?\s*$", re.I)
_ITEM = re.compile(r"^(?P<action>.*)\((?P<outcome>[^()]*?),\s*(?P<h>\d+(?:\.\d+)?)\s*hrs?\)\s*$")
_RETURNS = {"full": "full", "partial": "partial", "none": "none", "nil": "none", "no": "none"}


def _section(heading: str) -> str | None:
    h = heading.upper()
    if "CASING" in h or "CEMENT" in h:
        return "casing"
    if "MUD" in h:
        return "mud"
    if "PROBLEM" in h or "LESSON" in h:
        return "problems"
    if "TOPS" in h:
        return "tops"
    if "WELL DATA" in h:
        return "header"
    return "other"


def parse(lines: list[Line]) -> ParsedDocument:
    out = ParsedDocument()
    groups: dict[str, list[Line]] = {}
    where = "preamble"
    default_unit: str | None = None
    for ln in lines:
        t = ln.text.strip()
        if re.fullmatch(r"Page\s+\d+", t, re.I):
            continue
        if m := _HEADING.match(t):
            where = _section(m[2]) or "other"
            continue
        if m := _UNITS_LINE.search(t):
            default_unit = "m" if m[1].lower() == "metric" else "ft"
        groups.setdefault(where, []).append(ln)

    out.casing = _casing(groups.get("casing", []), default_unit, out.warnings)
    out.mud = _mud(groups.get("mud", []), default_unit, out.warnings)
    out.events = _problems(groups.get("problems", []), out.mud)
    return out


def _casing(lines: list[Line], default_unit: str | None, warnings: list[str]) -> list[CasingDraft]:
    unit = default_unit
    rows: list[CasingDraft] = []
    for ln in lines:
        if m := _CASING_HEADER.search(ln.text):
            unit = m[1].lower()
            continue
        tok = ln.text.split()
        if len(tok) < 4 or not any(c.isdigit() for c in tok[2]):
            continue  # noise or a non-row line
        returns = _RETURNS.get(tok[-1].lower().strip(".,")) if len(tok) >= 5 else None
        c = CasingDraft(
            od_in=rules.hole_size_in(tok[0]),
            hole_size_in=rules.hole_size_in(tok[1]),
            shoe_md_m=rules.depth_in_unit(tok[2], unit),
            toc_md_m=rules.depth_in_unit(tok[3], unit),
            returns=returns,
            lines=[ln],
        )
        if unit is None:
            c.penalties.add("depth unit not stated", 0.3)
        if c.od_in is None:
            c.penalties.add(f"casing size unreadable ({tok[0]!r})", 0.3)
        if c.hole_size_in is None:
            c.penalties.add(f"hole size unreadable ({tok[1]!r})", 0.2)
        if c.od_in and c.hole_size_in and c.od_in >= c.hole_size_in:
            c.penalties.add("casing is not smaller than its hole", 0.3)
        if c.shoe_md_m is None:
            c.penalties.add("shoe depth unreadable", 0.3)
        if c.toc_md_m is None:
            c.penalties.add(f"cement top unreadable ({tok[3]!r})", 0.2)
        elif c.shoe_md_m is not None and c.toc_md_m > c.shoe_md_m:
            c.penalties.add("cement top below the shoe", 0.3)
            c.toc_md_m = None
        if returns is None:
            c.penalties.add("cement returns unreadable", 0.1)
        rows.append(c)
    if lines and not rows:
        warnings.append("casing section present but no rows could be read")
    return rows


def _mud(lines: list[Line], default_unit: str | None, warnings: list[str]) -> list[MudDraft]:
    unit = default_unit
    rows: list[MudDraft] = []
    for ln in lines:
        if m := _MUD_HEADER.search(ln.text):
            unit = m[1].lower()
            continue
        m = _MUD_ROW.match(ln.text)
        if not m:
            continue
        top = rules.depth_in_unit(m[1], unit)
        base = rules.depth_in_unit(m[2], unit)
        if top is None or base is None or base <= top:
            warnings.append(f"mud interval unreadable: {ln.text!r}")
            continue
        d = MudDraft(
            md_from_m=top,
            md_to_m=base,
            hole_size_in=rules.hole_size_in(m[3]),
            mud_type=m[4].strip(),
            mw_sg=rules.mud_weight_sg(m[5]),
            lines=[ln],
        )
        if d.hole_size_in is None:
            d.penalties.add(f"hole size unreadable ({m[3]!r})", 0.2)
        if d.mw_sg is None or not 0.8 <= d.mw_sg <= 2.6:
            d.penalties.add("mud weight unreadable or implausible", 0.3)
            d.mw_sg = None
        rows.append(d)
    if lines and not rows:
        warnings.append("mud section present but no rows could be read")
    return rows


def _bullets(lines: list[Line]) -> list[tuple[date | None, list[Line]]]:
    out: list[tuple[date | None, list[Line]]] = []
    for ln in lines:
        if m := _BULLET.match(ln.text):
            try:
                day: date | None = date(int(m[1]), int(m[2]), int(m[3]))
            except ValueError:
                day = None
            out.append((day, [ln]))
        elif out:
            out[-1][1].append(ln)
    return out


def _split_items(text: str, offset: int) -> list[tuple[str, int, int]]:
    """Split 'a (x, 1 hrs); b (y, 2 hrs)' on semicolons outside parentheses."""
    items: list[tuple[str, int, int]] = []
    depth, start = 0, 0
    for k, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == ";" and depth == 0:
            items.append((text[start:k].strip(), offset + start, offset + k))
            start = k + 1
    items.append((text[start:].strip(), offset + start, offset + len(text)))
    return [i for i in items if i[0]]


def _problems(lines: list[Line], mud: list[MudDraft]) -> list[EventDraft]:
    events: list[EventDraft] = []
    for day, blines in _bullets(lines):
        joined = Joined(blines)
        text = _BULLET.sub(r"\4", joined.text, count=1)
        lead = len(joined.text) - len(text)
        parts = _ACTIONS.split(text, maxsplit=1)
        problem = parts[0].strip().rstrip(".")
        guess = rules.classify_event(problem)
        if guess is None:
            continue
        npt_total: float | None = None
        items: list[tuple[str, int, int]] = []
        if len(parts) == 2:
            rest = parts[1]
            rest_start = lead + text.index(rest, len(parts[0]))
            if m := _TAIL_NPT.search(rest):
                npt_total = float(m[1])
                rest = rest[: m.start()]
            items = _split_items(rest.strip().rstrip("."), rest_start)
        else:
            npt_total = rules.total_npt_hours(text)

        sub = rules.subtype(guess.event_type, problem)
        params = rules.event_params(guess.event_type, problem)
        md = rules.depth_m(problem)
        ev = EventDraft(
            event_type=guess.event_type,
            type_from_text=True,
            code_agrees=None,
            subtype=sub,
            severity=rules.severity(guess.event_type, sub, params),
            params=params,
            description=problem,
            primary=joined.lines_for(lead, lead + len(problem)),
            md_m=md,
            depth_votes=1 if md is not None else 0,
            formation_text=problem,
            header_formation=None,
            event_date=day,
            npt_hours=npt_total,
            npt_stated=npt_total is not None,
        )
        if md is None:
            ev.penalties.add("depth not stated", 0.25)
        if day is None:
            ev.penalties.add("date unreadable", 0.05)
        if md is not None:
            section = next((d for d in mud if d.md_from_m <= md <= d.md_to_m), None)
            if section is not None:
                ev.hole_size_in, ev.mw_sg = section.hole_size_in, section.mw_sg
                ev.supporting += section.lines
        for item, s, e in items:
            ev.mitigations.append(_mitigation(item, joined.lines_for(s, e)))
        if npt_total is not None and ev.mitigations:
            summed = sum(m.npt_hours or 0 for m in ev.mitigations)
            if abs(summed - npt_total) > 0.3:
                ev.penalties.add(
                    f"stated NPT {npt_total:g} h differs from the actions' {summed:g} h", 0.1
                )
        ev.supporting += [ln for ln in blines if ln not in ev.primary]
        events.append(ev)
    return events


def _mitigation(item: str, lines: list[Line]) -> MitigationDraft:
    m = _ITEM.match(item)
    action = (m["action"] if m else item).strip()
    outcome_text = m["outcome"].strip() if m else ""
    hours = float(m["h"]) if m else None
    code = rules.classify_action(action)
    outcome = rules.classify_outcome(outcome_text or action)
    mit = MitigationDraft(
        action_code=code,
        action_text=action,
        outcome=outcome,
        outcome_text=outcome_text,
        npt_hours=hours,
        lines=lines,
    )
    if code == "OTHER":
        mit.penalties.add("action not recognised", 0.3)
    if outcome == "unknown":
        mit.penalties.add("outcome not stated", 0.15)
    if hours is None:
        mit.penalties.add("duration not stated", 0.05)
    return mit
