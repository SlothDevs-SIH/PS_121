"""Rule-based document classification and header parsing (first-page text).

Rules come first (master plan §Stage 1): they are fast, explainable and tolerant of the
OCR noise seen on scanned reports. An LLM zero-shot fallback is planned for B2 for
documents the rules leave as OTHER.
"""

import re
from datetime import date

DOC_TYPES = (
    "DDR",
    "WCR",
    "MUD_LOG",
    "CASING_REPORT",
    "CEMENT_REPORT",
    "SURVEY",
    "GEO_REPORT",
    "OTHER",
)

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("DDR", re.compile(r"DAILY\s*DRILLING\s*REPORT|\bDDR\b", re.I)),
    ("WCR", re.compile(r"WELL\s*COMPLETION\s*REPORT|\bWCR\b", re.I)),
    ("MUD_LOG", re.compile(r"MUD\s*LOG(GING)?\s*(REPORT|DATA)?", re.I)),
    ("CEMENT_REPORT", re.compile(r"CEMENT(ING)?\s*JOB\s*REPORT", re.I)),
    ("CASING_REPORT", re.compile(r"CASING\s*TALLY|CASING\s*REPORT", re.I)),
    ("SURVEY", re.compile(r"DIRECTIONAL\s*SURVEY|SURVEY\s*REPORT", re.I)),
    ("GEO_REPORT", re.compile(r"GEOLOGICAL\s*REPORT|WELLSITE\s*GEOLOG", re.I)),
)

_WELL = re.compile(
    r"\bWell(?:\s*Name)?\s*[:\-]\s*(?P<name>[A-Za-z0-9#][A-Za-z0-9#/\-_. ]{1,30}?)"
    r"(?=\s+(?:Rig|Field|Report|Date|Operator)\b|\s{2,}|\s*$)",
    re.M,
)
# "Date:" on its own (not "Spud date:" / "Completion date:", which are other dates).
_REPORT_DATE = (
    re.compile(r"(?<![A-Za-z]\s)\bDate\s*[:\-]\s*(?P<d>\d{4}-\d{2}-\d{2})", re.I),
    re.compile(r"(?<![A-Za-z]\s)\bDate\s*[:\-]\s*(?P<d>\d{2}[./-]\d{2}[./-]\d{4})", re.I),
)
_COMPLETION_DATE = re.compile(r"\bCompletion\s*date\s*[:\-]\s*(?P<d>\d{4}-\d{2}-\d{2})", re.I)
_SYNTHETIC = re.compile(r"SYNTHETIC\s+DATA", re.I)


def classify(first_page_text: str) -> str:
    for doc_type, pattern in _RULES:
        if pattern.search(first_page_text):
            return doc_type
    return "OTHER"


def find_well_name(text: str) -> str | None:
    m = _WELL.search(text)
    return m.group("name").strip(" _.-") if m else None


def find_report_date(text: str, doc_type: str = "OTHER") -> date | None:
    """Report date; a completion report is dated by its completion date."""
    patterns = (_COMPLETION_DATE, *_REPORT_DATE) if doc_type == "WCR" else _REPORT_DATE
    for pat in patterns:
        m = pat.search(text)
        if not m:
            continue
        raw = m.group("d")
        try:
            if "-" in raw and len(raw.split("-")[0]) == 4:
                return date.fromisoformat(raw)
            d, mth, y = re.split(r"[./-]", raw)
            return date(int(y), int(mth), int(d))
        except ValueError:
            continue
    return None


def is_synthetic(text: str) -> bool:
    return bool(_SYNTHETIC.search(text))
