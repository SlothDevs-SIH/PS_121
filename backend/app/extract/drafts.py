"""Plain data passed from the document parsers (ddr.py, wcr.py) to the extraction service.

Parsers are pure: they read text lines (with span ids) and return drafts; only the service
touches the database. Every draft keeps the lines it came from, so every stored record
can cite its evidence spans.
"""

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class Line:
    span_id: int
    page_no: int
    text: str
    conf: float | None = None  # OCR confidence 0..100; None = PDF text layer
    x0: float = 0.0  # normalised left edge of the line's bounding box
    y: float = 0.0  # normalised vertical centre (0 = top of the page)


class Joined:
    """Several lines joined with single spaces, mapping character ranges back to lines."""

    def __init__(self, lines: list[Line]) -> None:
        self.lines = lines
        parts: list[str] = []
        self._starts: list[int] = []
        pos = 0
        for ln in lines:
            self._starts.append(pos)
            parts.append(ln.text.strip())
            pos += len(parts[-1]) + 1
        self.text = " ".join(parts)

    def lines_for(self, start: int, end: int) -> list[Line]:
        """Lines overlapping text[start:end]."""
        out = []
        for k, ln in enumerate(self.lines):
            s = self._starts[k]
            e = s + len(ln.text.strip())
            if s < end and e > start:
                out.append(ln)
        return out or self.lines[:1]


def ocr_confidence(lines: list[Line]) -> float:
    """Base confidence of a record from how its text was read: 0.95 for a PDF text layer,
    else the OCR engine's mean line confidence (capped at the same 0.95)."""
    confs = [ln.conf for ln in lines if ln.conf is not None]
    if not confs:
        return 0.95
    return round(min(0.95, sum(confs) / len(confs) / 100), 3)


@dataclass
class Penalties:
    """Reasons a record is less certain; each lowers its confidence by a fixed amount."""

    items: list[tuple[str, float]] = field(default_factory=list)

    def add(self, reason: str, amount: float) -> None:
        self.items.append((reason, amount))

    def apply(self, base: float) -> float:
        return round(max(0.05, min(1.0, base - sum(a for _, a in self.items))), 3)

    @property
    def reasons(self) -> list[str]:
        return [r for r, _ in self.items]


@dataclass
class MitigationDraft:
    action_code: str
    action_text: str
    outcome: str  # success | partial | fail | unknown
    outcome_text: str
    npt_hours: float | None
    lines: list[Line]
    t_start: datetime | None = None
    volume_m3: float | None = None
    penalties: Penalties = field(default_factory=Penalties)


@dataclass
class EventDraft:
    event_type: str
    type_from_text: bool
    code_agrees: bool | None
    subtype: str | None
    severity: str
    params: dict[str, float]
    description: str
    primary: list[Line]
    md_m: float | None
    depth_votes: int  # how many independent places in the document gave this depth
    formation_text: str | None  # where to look for the formation name (problem sentence)
    header_formation: str | None  # the report header's "Formation:" (a DDR's current bit)
    event_date: date | None
    t_start: datetime | None = None
    t_end: datetime | None = None
    hole_size_in: float | None = None
    mw_sg: float | None = None
    npt_hours: float | None = None
    npt_stated: bool = False  # the report states the total (vs summed from the time log)
    supporting: list[Line] = field(default_factory=list)
    mitigations: list[MitigationDraft] = field(default_factory=list)
    cause_text: str | None = None
    penalties: Penalties = field(default_factory=Penalties)

    @property
    def resolved(self) -> bool | None:
        outcomes = [m.outcome for m in self.mitigations]
        if "success" in outcomes:
            return True
        if outcomes and all(o == "fail" for o in outcomes):
            return False
        return None


@dataclass
class DdrOperationDraft:
    t_from: datetime | None
    t_to: datetime | None
    hours: float | None
    md_m: float | None
    code: str
    description: str
    lines: list[Line]
    event_index: int | None = None  # index into the document's EventDraft list


@dataclass
class CasingDraft:
    od_in: float | None
    hole_size_in: float | None
    shoe_md_m: float | None
    toc_md_m: float | None
    returns: str | None
    lines: list[Line]
    penalties: Penalties = field(default_factory=Penalties)


@dataclass
class MudDraft:
    md_from_m: float
    md_to_m: float
    hole_size_in: float | None
    mud_type: str | None
    mw_sg: float | None
    lines: list[Line]
    penalties: Penalties = field(default_factory=Penalties)


@dataclass
class ParsedDocument:
    """Everything one report yields. Empty lists are normal (a DDR with no problems)."""

    report_date: date | None = None
    events: list[EventDraft] = field(default_factory=list)
    operations: list[DdrOperationDraft] = field(default_factory=list)
    casing: list[CasingDraft] = field(default_factory=list)
    mud: list[MudDraft] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
