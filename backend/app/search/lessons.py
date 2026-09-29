"""Lessons-learned cards (S5): problem -> likely cause -> action taken -> outcome -> lesson.

Written from the event's extracted fields by a fixed template, so every sentence is
traceable to the event's evidence; nothing is added that the reports do not say. Wording
is advisory ("consider"), and a card describes one event: it never claims a success rate
(that is the Mitigation Effectiveness Ledger's job, across wells).
"""

from typing import Any

from app.db.models import Event

TEMPLATE_VERSION = "template:v1"

_LABELS = {
    "LOSS": "Lost circulation",
    "KICK": "Kick",
    "STUCK": "Stuck pipe",
    "TIGHT": "Tight hole",
    "TORQUE": "High torque",
    "INSTAB": "Wellbore instability",
    "BALLING": "Bit balling",
    "OVERP": "Overpressure indications",
    "GAS": "Gas",
    "CEMENT": "Cementing problem",
    "CASING": "Casing problem",
    "FISH": "Fishing",
    "EQUIP": "Equipment failure",
    "WAIT": "Waiting",
    "OTHER_NPT": "Non-productive time",
}
_PARAM_TEXT = {
    "loss_rate_m3_h": "loss rate {:.1f} m3/h",
    "pit_gain_m3": "pit gain {:.1f} m3",
    "sidpp_kpa": "SIDPP {:.0f} kPa",
    "overpull_kn": "overpull {:.0f} kN",
    "torque_knm": "torque {:.1f} kN.m",
    "gas_pct": "gas {:.1f}%",
}
_CAUSE_BY_SUBTYPE = {
    ("STUCK", "differential"): "Differential sticking, as stated in the report",
    ("STUCK", "pack-off"): "Pack-off, as stated in the report",
    ("STUCK", "mechanical"): "Mechanical sticking, as stated in the report",
    ("CEMENT", "losses during cementing"): "Losses while cementing, as stated in the report",
    ("CEMENT", "poor bond"): "Poor cement bond, as stated in the report",
}


def label(event_type: str) -> str:
    return _LABELS.get(event_type, event_type)


def build(ev: Event, formation: str | None) -> dict[str, Any]:
    where = f" at {ev.md_m:.0f} m MD" if ev.md_m is not None else ""
    if formation:
        where += f" in {formation}"
    what = label(ev.event_type) + (f" ({ev.subtype})" if ev.subtype else "")
    facts = [_PARAM_TEXT[k].format(v) for k, v in (ev.params or {}).items() if k in _PARAM_TEXT]
    if ev.hole_size_in:
        facts.append(f'{ev.hole_size_in:g}" hole')
    if ev.mw_sg:
        facts.append(f"mud weight {ev.mw_sg:.2f} SG")
    problem = what + where + (f"; {', '.join(facts)}" if facts else "") + "."

    cause = ev.cause_text or _CAUSE_BY_SUBTYPE.get((ev.event_type, ev.subtype or ""))
    mits = sorted(ev.mitigations, key=lambda m: m.seq)
    action_taken = (
        "; ".join(f"{m.seq}. {m.action_text or m.action_code} ({m.outcome})" for m in mits) or None
    )
    npt = f"{ev.npt_hours:g} h NPT" if ev.npt_hours is not None else "NPT not stated"
    wins = [m for m in mits if m.outcome == "success"]
    outcome: str | None
    fails = [m for m in mits if m.outcome == "fail"]
    if wins:
        first_win = wins[0]
        attempts = mits.index(first_win) + 1
        outcome = (
            f"Resolved by '{first_win.action_text or first_win.action_code}'"
            f" on attempt {attempts} of {len(mits)}; {npt}."
        )
    elif mits and len(fails) == len(mits):
        outcome = f"Not resolved by the recorded actions; {npt}."
    else:
        outcome = f"Outcome not stated; {npt}." if mits else None

    lesson: str | None = None
    ctx = f"{label(ev.event_type).lower()}" + (f" in {formation}" if formation else "")
    if wins and fails and mits.index(wins[0]) > 0:
        tried = ", ".join(f"'{m.action_text or m.action_code}'" for m in fails[:3])
        lesson = (
            f"Here {tried} did not work before '{wins[0].action_text or wins[0].action_code}'"
            f" did. For similar {ctx}, consider trying it earlier; this is one event, so"
            " check the ledger across offset wells before relying on it."
        )
    elif wins:
        lesson = (
            f"'{wins[0].action_text or wins[0].action_code}' worked on the first attempt"
            f" for this {ctx}; one event, so check the ledger across offset wells."
        )
    elif mits and len(fails) == len(mits):
        lesson = (
            f"None of the recorded actions resolved this {ctx}; review offset wells"
            " before relying on them."
        )
    return {
        "problem": problem,
        "likely_cause": cause,
        "action_taken": action_taken,
        "outcome": outcome,
        "lesson": lesson,
        "generated_by": TEMPLATE_VERSION,
    }
