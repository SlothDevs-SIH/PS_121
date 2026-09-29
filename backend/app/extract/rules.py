"""Deterministic extraction rules (S2 "rules" pass): units, event types, actions, outcomes.

Pure functions over text, so every rule is unit-tested. Phrase lists are drilling
vocabulary (as a wellsite engineer writes it), deliberately not copied from the synthetic
generator's templates: the evaluation (``scripts/eval_extraction.py``) then measures real
generalisation on reworded reports rather than a lookup of our own sentences.

All returned numbers are canonical SI (m, SG, m3, m3/h, kN, kN.m, kPa) via app.core.units.
"""

import re
from dataclasses import dataclass

from app.core import units

# ─── Numbers and units ────────────────────────────────────────────────────────────────────

_NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"


def parse_number(raw: str) -> float:
    return float(raw.replace(",", ""))


_DEPTH = re.compile(_NUM + r"\s*(m|ft|feet|metres|meters)\b(?!\s*/)", re.I)
_MW = re.compile(_NUM + r"\s*(SG|ppg|sg)\b")
_RATE = re.compile(_NUM + r"\s*(bbl|m3|m³)\s*/\s*(?:hr|h)\b", re.I)
_VOLUME = re.compile(_NUM + r"\s*(bbl|m3|m³)\b(?!\s*/)", re.I)
_KLBF = r"\s*k[l1Ii]bf"  # tolerates the usual OCR misreads (kibf, k1bf)
_OVERPULL = re.compile(
    r"overpull\s*(?:of\s*)?" + _NUM + _KLBF + "|" + _NUM + _KLBF + r"\s*overpull", re.I
)
_TORQUE = re.compile(_NUM + r"\s*kft[.\s-]*[l1I]bf", re.I)
_PSI = r"\s*[:=]?\s*" + _NUM + r"\s*psi"
_SIDPP = re.compile(r"SIDPP" + _PSI, re.I)
_SICP = re.compile(r"SICP" + _PSI, re.I)
_GAS_PCT = re.compile(_NUM + r"\s*%")
_FRACTION = re.compile(r"^(\d+)(?:[-\s](\d+)/(\d+))?$")


def depth_m(text: str) -> float | None:
    """First depth with an explicit unit, in metres."""
    m = _DEPTH.search(text)
    if not m:
        return None
    value = parse_number(m.group(1))
    return units.ft_to_m(value) if m.group(2).lower() in ("ft", "feet") else value


def depth_in_unit(raw: str, unit: str | None) -> float | None:
    """A bare table-column number in the column's unit ('m' or 'ft'), in metres."""
    try:
        value = parse_number(raw)
    except ValueError:
        return None
    if unit is None:
        return None
    return units.ft_to_m(value) if unit == "ft" else value


def mud_weight_sg(text: str) -> float | None:
    m = _MW.search(text)
    if not m:
        return None
    value = parse_number(m.group(1))
    return value if m.group(2).lower() == "sg" else units.ppg_to_sg(value)


def rate_m3_h(text: str) -> float | None:
    m = _RATE.search(text)
    if not m:
        return None
    value = parse_number(m.group(1))
    return units.bbl_to_m3(value) if m.group(2).lower() == "bbl" else value


def volume_m3(text: str) -> float | None:
    m = _VOLUME.search(text)
    if not m:
        return None
    value = parse_number(m.group(1))
    return units.bbl_to_m3(value) if m.group(2).lower() == "bbl" else value


def overpull_kn(text: str) -> float | None:
    m = _OVERPULL.search(text)
    if not m:
        return None
    return units.klbf_to_kn(parse_number(m.group(1) or m.group(2)))


def torque_knm(text: str) -> float | None:
    m = _TORQUE.search(text)
    return units.kftlbf_to_knm(parse_number(m.group(1))) if m else None


def psi_to_kpa_match(pattern: re.Pattern[str], text: str) -> float | None:
    m = pattern.search(text)
    return units.psi_to_kpa(parse_number(m.group(1))) if m else None


def sidpp_kpa(text: str) -> float | None:
    return psi_to_kpa_match(_SIDPP, text)


def sicp_kpa(text: str) -> float | None:
    return psi_to_kpa_match(_SICP, text)


def gas_pct(text: str) -> float | None:
    if "gas" not in text.lower():
        return None
    m = _GAS_PCT.search(text)
    return parse_number(m.group(1)) if m else None


def hole_size_in(raw: str) -> float | None:
    """Nominal size designation: '12-1/4' → 12.25, '9 5/8' → 9.625, '7' → 7.0."""
    m = _FRACTION.match(raw.strip().rstrip('"').replace(" in", "").strip())
    if not m:
        return None
    whole = float(m.group(1))
    if m.group(2):
        whole += float(m.group(2)) / float(m.group(3))
    return whole


# ─── Event classification ──────────────────────────────────────────────────────────────────

# Order matters: the first match wins (a cement job with losses is a CEMENT problem).
_EVENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "CEMENT",
        re.compile(
            r"\bcement(?:ing)?\s+(?:job|problem)|during cementing|poor (?:cement )?bond", re.I
        ),
    ),
    ("KICK", re.compile(r"\bkick(?:ed)?\b|\bpit gain\b|\binflux\b|\bflowed\b", re.I)),
    (
        "OVERP",
        re.compile(r"overpressur|high (?:background )?gas|connection gas|gas readings", re.I),
    ),
    (
        "LOSS",
        re.compile(
            r"lost circulation|\blosses?\b|\blost returns\b|no returns|partial returns", re.I
        ),
    ),
    ("STUCK", re.compile(r"\bstuck\b|\bsticking\b|\bpack[- ]?off\b", re.I)),
    ("TIGHT", re.compile(r"\btight\s+(?:hole|spot)\b|\bdrag\b", re.I)),
    ("TORQUE", re.compile(r"\btorque\b", re.I)),
    ("INSTAB", re.compile(r"instabilit|\bcavings\b|sloughing|washout|swelling", re.I)),
    ("BALLING", re.compile(r"\bballing\b|\bballed\b", re.I)),
    ("FISH", re.compile(r"\bfishing\b|\bfish\b", re.I)),
    ("EQUIP", re.compile(r"\brepair\b|\bfailure\b|\bbreakdown\b", re.I)),
    ("WAIT", re.compile(r"\bwaiting\b|\bwait(?:ed)?\s+on\b", re.I)),
)

# DDR time-log NPT codes → the event type they imply when the text is silent.
_CODE_TYPES = {
    "NPT-LOSS": "LOSS",
    "NPT-STCK": "STUCK",
    "NPT-STUCK": "STUCK",
    "NPT-WC": "KICK",
    "NPT-CMT": "CEMENT",
    "NPT-FISH": "FISH",
    "NPT-RIG": "EQUIP",
    "NPT-WAIT": "WAIT",
}
# Types consistent with a code (text classification must agree to be trusted fully).
_CODE_COMPATIBLE = {
    "NPT-LOSS": {"LOSS"},
    "NPT-STCK": {"STUCK", "TIGHT"},
    "NPT-STUCK": {"STUCK", "TIGHT"},
    "NPT-WC": {"KICK", "OVERP", "GAS"},
    "NPT-CMT": {"CEMENT", "LOSS"},
    "NPT-HOLE": {"TIGHT", "TORQUE", "INSTAB", "BALLING", "STUCK"},
}


@dataclass(frozen=True)
class TypeGuess:
    event_type: str
    from_text: bool  # False = only the NPT code said so (lower confidence)
    code_agrees: bool | None  # None when there was no code


def classify_event(text: str, code: str | None = None) -> TypeGuess | None:
    text_type = next((t for t, p in _EVENT_PATTERNS if p.search(text)), None)
    code = (code or "").upper() or None
    if text_type:
        agrees = None if code is None else text_type in _CODE_COMPATIBLE.get(code, {text_type})
        return TypeGuess(text_type, True, agrees)
    if code and code in _CODE_TYPES:
        return TypeGuess(_CODE_TYPES[code], False, True)
    if code and code.startswith("NPT"):
        return TypeGuess("OTHER_NPT", False, True)
    return None


_SUBTYPES: dict[str, re.Pattern[str]] = {
    "LOSS": re.compile(r"\b(seepage|partial|severe|total)\b", re.I),
    "STUCK": re.compile(r"\b(differential|pack-off|mechanical)\b", re.I),
    "INSTAB": re.compile(r"\b(cavings|sloughing|washout|swelling)\b", re.I),
    "CEMENT": re.compile(r"(losses during cementing|poor (?:cement )?bond|channel+ing)", re.I),
    "KICK": re.compile(r"\b(gas|water|oil)\s+(?:kick|influx)\b", re.I),
}


def subtype(event_type: str, text: str) -> str | None:
    pattern = _SUBTYPES.get(event_type)
    m = pattern.search(text) if pattern else None
    return m.group(1).lower() if m else None


# Loss severity by rate follows common industry bands (seepage < 10 bbl/h, partial 10-100,
# severe > 100, total = no returns); configurable per OIL practice later.
_SEEPAGE_M3_H = units.bbl_to_m3(10)
_PARTIAL_M3_H = units.bbl_to_m3(100)
_OVERPULL_MEDIUM_KN = units.klbf_to_kn(45)
_TORQUE_MEDIUM_KNM = units.kftlbf_to_knm(25)


def severity(event_type: str, sub: str | None, params: dict[str, float]) -> str:
    if event_type == "LOSS":
        if sub in ("severe", "total"):
            return "high"
        if sub == "seepage":
            return "low"
        if sub == "partial":
            return "medium"
        rate = params.get("loss_rate_m3_h")
        if rate is None:
            return "medium"
        return "low" if rate < _SEEPAGE_M3_H else ("medium" if rate <= _PARTIAL_M3_H else "high")
    if event_type == "KICK":
        return "high"
    if event_type == "STUCK":
        return "high" if sub == "differential" else "medium"
    if event_type == "TIGHT":
        op = params.get("overpull_kn")
        return "low" if op is not None and op < _OVERPULL_MEDIUM_KN else "medium"
    if event_type == "TORQUE":
        tq = params.get("torque_knm")
        return "low" if tq is not None and tq < _TORQUE_MEDIUM_KNM else "medium"
    return "medium"


def event_params(event_type: str, text: str) -> dict[str, float]:
    """Type-specific numbers (keys as api.v1.schemas.events.EventParams)."""
    found: dict[str, float | None] = {}
    if event_type == "LOSS":
        found["loss_rate_m3_h"] = rate_m3_h(text)
    if event_type == "KICK":
        found["pit_gain_m3"] = volume_m3(text)
        found["sidpp_kpa"] = sidpp_kpa(text)
        found["sicp_kpa"] = sicp_kpa(text)
    if event_type in ("STUCK", "TIGHT"):
        found["overpull_kn"] = overpull_kn(text)
    if event_type == "TORQUE":
        found["torque_knm"] = torque_knm(text)
    if event_type in ("OVERP", "GAS", "KICK"):
        found["gas_pct"] = gas_pct(text)
    return {k: round(v, 3) for k, v in found.items() if v is not None}


# ─── Mitigation actions and outcomes ───────────────────────────────────────────────────────

_ACTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("LCM_PILL_COARSE", re.compile(r"\bcoarse\b[^.;]*\bLCM\b|\bLCM\b[^.;]*\bcoarse\b", re.I)),
    ("LCM_PILL_FINE", re.compile(r"\bfine\b[^.;]*\bLCM\b|\bLCM\b[^.;]*\bfine\b", re.I)),
    ("LCM_BACKGROUND", re.compile(r"background LCM|LCM in (?:the )?system", re.I)),
    ("CEMENT_PLUG", re.compile(r"cement plug", re.I)),
    ("REMEDIAL_SQUEEZE", re.compile(r"\bsqueez", re.I)),
    ("TOP_JOB", re.compile(r"\btop job\b", re.I)),
    (
        "REDUCE_MW",
        re.compile(
            r"(?:reduc|cut back|lower|decreas)\w*\s+(?:the\s+)?mud weight|\bMW\s+(?:reduced|cut)",
            re.I,
        ),
    ),
    (
        "INCREASE_MW",
        re.compile(
            r"(?:rais|increas|weight(?:ed)? up)\w*\s+(?:the\s+)?mud weight|weighted up", re.I
        ),
    ),
    (
        "REDUCE_FLOW_RATE",
        re.compile(r"(?:reduc|lower|decreas|cut)\w*\s+(?:the\s+)?(?:flow|pump)\s*rate", re.I),
    ),
    (
        "INCREASE_FLOW",
        re.compile(r"(?:increas|rais)\w*\s+(?:the\s+)?(?:flow|pump|circulation)\s*rate", re.I),
    ),
    ("SPOT_PIPE_RELEASE_PILL", re.compile(r"pipe[- ](?:release|freeing)|spotting fluid", re.I)),
    ("JAR_DOWN", re.compile(r"jarr?(?:ed|ing)?\s+down|jars? downward", re.I)),
    ("JAR_UP", re.compile(r"jarr?(?:ed|ing)?\s+up|jars? upward|worked jars", re.I)),
    ("BACKOFF_AND_FISH", re.compile(r"back(?:ed)?[- ]off", re.I)),
    ("FISHING", re.compile(r"\bfishing\b|\bfished\b", re.I)),
    ("SIDETRACK", re.compile(r"sidetrack", re.I)),
    ("WORK_PIPE", re.compile(r"worked\s+(?:the\s+)?(?:pipe|string)|working pipe", re.I)),
    ("WAIT_AND_WEIGHT", re.compile(r"wait[- ]and[- ]weight|engineer'?s method", re.I)),
    ("DRILLERS_METHOD", re.compile(r"driller'?s method", re.I)),
    ("BULLHEAD", re.compile(r"bullhead", re.I)),
    ("REAM", re.compile(r"\b(?:back-?)?ream", re.I)),
    ("WIPER_TRIP", re.compile(r"wiper trip|short trip", re.I)),
    ("ADD_LUBRICANT", re.compile(r"lubricant", re.I)),
    ("REDUCE_RPM", re.compile(r"(?:reduc|lower)\w*\s+(?:the\s+)?(?:rotary speed|rpm)", re.I)),
    ("ADD_DETERGENT", re.compile(r"detergent", re.I)),
    ("CHANGE_BHA", re.compile(r"chang\w*\s+(?:the\s+)?BHA|new bit", re.I)),
    ("CIRCULATE", re.compile(r"(?<!lost )\bcirculat(?:e|ed|ing)\b", re.I)),
)

_FAIL = re.compile(
    r"not successful|unsuccessful|without success|no improvement|did not|failed|no change", re.I
)
_SUCCESS = re.compile(
    r"\bcured\b|regained|\bfreed\b|came free|under control|\bkilled\b|hole free|no further drag|"
    r"back to (?:normal|background)|stabili[sz]ed|\bstable\b|\breduced\b|recovered|cleaned up|"
    r"restored|confirmed|successful",
    re.I,
)


def classify_action(text: str) -> str:
    return next((code for code, p in _ACTION_PATTERNS if p.search(text)), "OTHER")


def is_action(text: str) -> bool:
    return classify_action(text) != "OTHER"


def classify_outcome(text: str) -> str:
    if _FAIL.search(text):
        return "fail"
    if _SUCCESS.search(text):
        return "success"
    return "unknown"


_OUTCOME_SPLIT = re.compile(r"\s+[-\u2013\u2014:]\s+(?=[^-\u2013\u2014:]*$)")


def split_action_outcome(text: str) -> tuple[str, str]:
    """'Pumped 40 bbl coarse LCM pill - losses cured' → (action, outcome text)."""
    parts = _OUTCOME_SPLIT.split(text.strip(), maxsplit=1)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else (text.strip(), "")


_NPT_TOTAL = re.compile(r"(?:total\s+)?NPT\s*[:=]?\s*" + _NUM + r"\s*(?:hrs?|hours?)\b", re.I)


def total_npt_hours(text: str) -> float | None:
    m = _NPT_TOTAL.search(text)
    return parse_number(m.group(1)) if m else None
