"""Daily Drilling Report parser: header facts, the time log, and the NPT events in it.

A DDR covers one day (00:00-24:00). Its time log is a table; every non-productive-time
(NPT) episode starts with a row describing the problem and continues with rows for the
actions taken ("<action> - <outcome>"). The REMARKS paragraph repeats the story and usually
states the total NPT. Parsing tolerates what OCR does to such tables: stray punctuation
after times, lost decimal points ("05" for 0.5 h), rule lines read as noise, and wrapped
operation cells whose first line sits above the row.
"""

import re
from datetime import date, datetime, time, timedelta, timezone

from app.extract import rules
from app.extract.drafts import (
    DdrOperationDraft,
    EventDraft,
    Line,
    MitigationDraft,
    ParsedDocument,
)

# Reports are written in Indian Standard Time, which has no daylight saving.
IST = timezone(timedelta(hours=5, minutes=30), "IST")

_DATE_ISO = re.compile(r"Date\s*[:.]?\s*(\d{4})-(\d{2})-(\d{2})", re.I)
_DATE_DMY = re.compile(r"Date\s*[:.]?\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", re.I)
_HEADER_DEPTH = re.compile(r"Depth\s+at\s+\d{1,2}\s*[:.]?\s*\d{2}\s*[:.;]?\s*(.*)", re.I)
_HOLE = re.compile(r"Hole\s*size\s*[:.;]?\s*(\d{1,2}(?:[-\s]\d{1,2}/\d{1,2})?)", re.I)
_MUD_WEIGHT = re.compile(r"Mud\s*weight\s*[:.;]?\s*(.*)", re.I)
_FORMATION = re.compile(r"Formation\s*[:.;]\s*(.+)$", re.I)
_LOG_HEADER = re.compile(r"\bFrom\b.*\bTo\b.*Depth\s*\(?\s*(m|ft)\b", re.I)
_TIME = r"(\d{1,2})\s?[:.;]?\s?(\d{2})(?!\d)"  # OCR sometimes drops the colon
_JUNK = r"[^\w\s]*\s+(?:[^\w\s]+\s+)*[^\w\s]*"  # punctuation OCR sprinkles between cells
_ROW = re.compile(
    r"^\s*"
    + _TIME
    + _JUNK
    + _TIME
    + _JUNK
    # Hrs may be garbled into two tokens ("he SJ"); the second never starts with a digit.
    + r"(\S+(?:\s+[^\s\d]\S*)?)\s+([\d,.]+)\s+"
    r"([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)?)\b\s*(.*)$"
)
_SECTION = re.compile(r"^\s*(TIME LOG|REMARKS|MUD|BHA|PERSONNEL|HSE)\s*$", re.I)
_CAUSE = re.compile(r"\b(?:due to|caused by)\s+([^.;]+)", re.I)

# Activity codes → the operation phase they belong to (unknown codes keep phase empty).
_PHASES = {
    "DRL": "DRILLING",
    "CIRC": "CIRCULATING",
    "TRIP": "TRIPPING",
    "CSG": "CASING",
    "CMT": "CEMENTING",
    "LOG": "LOGGING",
    "RIG": "RIG_UP",
}
DEPTH_AGREE_M = 1.0  # sources rounding to whole feet/metres agree within this


def report_date(lines: list[Line]) -> date | None:
    for ln in lines[:8]:
        if m := _DATE_ISO.search(ln.text):
            try:
                return date(int(m[1]), int(m[2]), int(m[3]))
            except ValueError:
                return None
        if m := _DATE_DMY.search(ln.text):
            try:
                return date(int(m[3]), int(m[2]), int(m[1]))  # day-first, as written in India
            except ValueError:
                return None
    return None


def _clock(day: date | None, hh: str, mm: str) -> datetime | None:
    if day is None:
        return None
    h, m = int(hh), int(mm)
    if h == 24 and m == 0:
        return datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=IST)
    if h > 23 or m > 59:
        return None
    return datetime.combine(day, time(h, m), tzinfo=IST)


class _Row:
    def __init__(self, line: Line, m: re.Match[str], day: date | None, unit: str | None):
        self.line = line
        self.t_from = _clock(day, m[1], m[2])
        self.t_to = _clock(day, m[3], m[4])
        self.stated_hours = m[5]
        self.md_m = rules.depth_in_unit(m[6].rstrip("."), unit)
        self.code = m[7].upper()
        self.own_text = m[8].strip()
        self.above: list[Line] = []  # wrapped operation-cell lines, by vertical position
        self.below: list[Line] = []

    def roll_after(self, previous: "_Row | None") -> None:
        """Operations can run past midnight: keep times increasing through the log."""
        if self.t_from is None:
            return
        if previous is not None and previous.t_to is not None:
            while self.t_from < previous.t_to - timedelta(minutes=30):
                self.t_from += timedelta(days=1)
                if self.t_to is not None:
                    self.t_to += timedelta(days=1)
        if self.t_to is not None and self.t_to < self.t_from:
            self.t_to += timedelta(days=1)

    @property
    def hours(self) -> float | None:
        # Times are more robust to OCR than the Hrs column (which loses decimal points).
        if self.t_from and self.t_to:
            return round((self.t_to - self.t_from).total_seconds() / 3600, 2)
        try:
            return float(self.stated_hours)
        except ValueError:
            return None

    @property
    def lines(self) -> list[Line]:
        return [*self.above, self.line, *self.below]

    @property
    def text(self) -> str:
        parts = [ln.text.strip() for ln in self.above]
        parts.append(self.own_text)
        parts += [ln.text.strip() for ln in self.below]
        return " ".join(p for p in parts if p)

    @property
    def is_npt(self) -> bool:
        return self.code.startswith("NPT")


def _header(lines: list[Line]) -> tuple[dict[str, object], list[Line]]:
    facts: dict[str, object] = {}
    used: list[Line] = []
    for ln in lines[:10]:
        t = ln.text
        hit = False
        if m := _HEADER_DEPTH.search(t):
            facts["depth_m"] = rules.depth_m(m[1].split("Hole")[0])
            hit = True
        if m := _HOLE.search(t):
            facts["hole_size_in"] = rules.hole_size_in(m[1])
            hit = True
        if m := _MUD_WEIGHT.search(t):
            facts["mw_sg"] = rules.mud_weight_sg(m[1])
            hit = True
        if m := _FORMATION.search(t):
            facts["formation"] = m[1].strip()
            hit = True
        if hit:
            used.append(ln)
        if _LOG_HEADER.search(t) or t.strip().upper() == "TIME LOG":
            break
    return facts, used


def _sections(lines: list[Line]) -> tuple[list[Line], list[Line], str | None]:
    """(time-log lines, remarks lines, depth column unit)."""
    log: list[Line] = []
    remarks: list[Line] = []
    unit: str | None = None
    where = "head"
    for ln in lines:
        t = ln.text.strip()
        if sec := _SECTION.match(t):
            where = sec[1].upper()
            continue
        if m := _LOG_HEADER.search(t):
            unit = m[1].lower()
            where = "TIME LOG"
            continue
        if re.fullmatch(r"Page\s+\d+", t, re.I):
            continue
        if where == "TIME LOG":
            log.append(ln)
        elif where == "REMARKS":
            remarks.append(ln)
    return log, remarks, unit


def _rows(log: list[Line], day: date | None, unit: str | None) -> list[_Row]:
    rows: list[_Row] = []
    loose: list[Line] = []
    for ln in log:
        m = _ROW.match(ln.text)
        if m:
            row = _Row(ln, m, day, unit)
            row.roll_after(rows[-1] if rows else None)
            rows.append(row)
        else:
            loose.append(ln)
    if not rows:
        return rows
    # Wrapped operation-cell text sits in the operation column, to the right of the row
    # start; anything else in the table area (OCR'd rule lines) is noise.
    left = min(r.line.x0 for r in rows)
    for ln in loose:
        if ln.x0 < left + 0.15 or (ln.conf is not None and ln.conf < 50):
            continue
        # A wrapped cell is centred on its row, whose own operation cell is then empty.
        nearest = min(
            (r for r in rows if r.line.page_no == ln.page_no),
            key=lambda r: abs(r.line.y - ln.y) + (0.01 if r.own_text else 0.0),
            default=None,
        )
        if nearest is None:
            continue
        (nearest.above if ln.y < nearest.line.y else nearest.below).append(ln)
    return rows


def _vote_depth(candidates: list[tuple[str, float | None]]) -> tuple[float | None, int, bool]:
    """Pick the depth most sources agree on: (depth, votes, sources_conflict)."""
    vals = [(src, v) for src, v in candidates if v is not None]
    if not vals:
        return None, 0, False
    best: tuple[float | None, int] = (None, 0)
    for _, v in vals:
        n = sum(1 for _, w in vals if abs(w - v) <= DEPTH_AGREE_M)
        if n > best[1]:
            best = (v, n)
    return best[0], best[1], best[1] < len(vals)


def parse(lines: list[Line]) -> ParsedDocument:
    out = ParsedDocument()
    day = report_date(lines)
    out.report_date = day
    head, head_lines = _header(lines)
    log, remarks, unit = _sections(lines)
    if unit is None:
        out.warnings.append("time log depth unit not found")
    rows = _rows(log, day, unit)
    if not rows and log:
        out.warnings.append("time log present but no rows could be read")

    current: EventDraft | None = None
    current_code: str | None = None
    event_rows: list[list[_Row]] = []
    for row in rows:
        op = DdrOperationDraft(
            t_from=row.t_from,
            t_to=row.t_to,
            hours=row.hours,
            md_m=row.md_m,
            code=row.code,
            description=row.text,
            lines=row.lines,
        )
        out.operations.append(op)
        if not row.is_npt:
            current, current_code = None, None
            continue
        text = row.text
        action, outcome = rules.split_action_outcome(text)
        if current is not None and rules.is_action(action):
            current.mitigations.append(_mitigation(row, action, outcome))
            op.event_index = len(out.events) - 1
            event_rows[-1].append(row)
            continue
        guess = rules.classify_event(text, row.code)
        new_type_in_text = guess is not None and guess.from_text
        if (
            current is not None
            and row.code == current_code
            and not (
                new_type_in_text and guess is not None and guess.event_type != current.event_type
            )
        ):
            # Same NPT episode, not a recognisable action: keep it, flagged as OTHER.
            mit = _mitigation(row, action, outcome)
            current.mitigations.append(mit)
            op.event_index = len(out.events) - 1
            event_rows[-1].append(row)
            continue
        if guess is None:
            continue
        current = _event(row, guess, head, head_lines, day)
        current_code = row.code
        if rules.is_action(action) and rules.classify_outcome(outcome) != "unknown":
            # No problem row: the episode starts with an action. The event is inferred.
            current.penalties.add("problem not described; inferred from the action taken", 0.15)
            current.mitigations.append(_mitigation(row, action, outcome))
        out.events.append(current)
        event_rows.append([row])
        op.event_index = len(out.events) - 1

    stated_total = rules.total_npt_hours(" ".join(ln.text for ln in remarks))
    for ev, ev_rows in zip(out.events, event_rows, strict=True):
        _finish_npt(ev, ev_rows, stated_total if len(out.events) == 1 else None)
        if len(out.events) == 1:
            ev.supporting += remarks
    return out


def _event(
    row: _Row,
    guess: rules.TypeGuess,
    head: dict[str, object],
    head_lines: list[Line],
    day: date | None,
) -> EventDraft:
    text = row.text
    sub = rules.subtype(guess.event_type, text)
    params = rules.event_params(guess.event_type, text)
    header_depth = head.get("depth_m")
    md, votes, conflict = _vote_depth(
        [
            ("text", rules.depth_m(text)),
            ("column", row.md_m),
            ("header", header_depth if isinstance(header_depth, float) else None),
        ]
    )
    hole = head.get("hole_size_in")
    mw = head.get("mw_sg")
    fm = head.get("formation")
    ev = EventDraft(
        event_type=guess.event_type,
        type_from_text=guess.from_text,
        code_agrees=guess.code_agrees,
        subtype=sub,
        severity=rules.severity(guess.event_type, sub, params),
        params=params,
        description=text,
        primary=row.lines,
        md_m=md,
        depth_votes=votes,
        formation_text=text,
        header_formation=fm if isinstance(fm, str) else None,
        event_date=day,
        t_start=row.t_from,
        t_end=row.t_to,
        hole_size_in=hole if isinstance(hole, float) else None,
        mw_sg=mw if isinstance(mw, float) else None,
        supporting=list(head_lines),
    )
    if m := _CAUSE.search(text):
        ev.cause_text = m[1].strip()
    if not guess.from_text:
        ev.penalties.add(f"event type taken from the NPT code {row.code} only", 0.2)
    elif guess.code_agrees is False:
        ev.penalties.add(f"text says {guess.event_type} but the NPT code is {row.code}", 0.1)
    if md is None:
        ev.penalties.add("depth not stated", 0.25)
    elif conflict:
        ev.penalties.add("depth sources in the report disagree", 0.1)
    elif votes == 1 and rules.depth_m(text) is None:
        ev.penalties.add("depth only from the time-log column", 0.05)
    return ev


def _mitigation(row: _Row, action: str, outcome_text: str) -> MitigationDraft:
    code = rules.classify_action(action)
    outcome = rules.classify_outcome(outcome_text or action)
    mit = MitigationDraft(
        action_code=code,
        action_text=action,
        outcome=outcome,
        outcome_text=outcome_text,
        npt_hours=row.hours,
        lines=row.lines,
        t_start=row.t_from,
    )
    if code == "OTHER":
        mit.penalties.add("action not recognised", 0.3)
    if outcome == "unknown":
        mit.penalties.add("outcome not stated", 0.15)
    if row.hours is None:
        mit.penalties.add("duration unreadable", 0.05)
    return mit


def _finish_npt(ev: EventDraft, rows: list[_Row], stated: float | None) -> None:
    ev.t_end = rows[-1].t_to or ev.t_end
    hours = [r.hours for r in rows]
    all_rows = round(sum(h for h in hours if h is not None), 2) if any(hours) else None
    actions = round(sum(h for h in hours[1:] if h is not None), 2) if len(rows) > 1 else None
    if stated is not None:
        agrees = any(v is not None and abs(v - stated) <= 0.3 for v in (all_rows, actions))
        if agrees or all_rows is None:
            ev.npt_hours, ev.npt_stated = stated, True
            return
        ev.penalties.add(
            f"remarks state {stated:g} h NPT but the time log sums to {all_rows:g} h", 0.1
        )
    ev.npt_hours = round(all_rows, 1) if all_rows is not None else None


def phase(code: str) -> str | None:
    if code.startswith("NPT"):
        return "NPT"
    return _PHASES.get(code)


def npt_category(code: str) -> str | None:
    return code.split("-", 1)[1] if code.startswith("NPT-") else None
