"""Copilot answers: plan → read-only tools → a cited answer, streamed as events.

Every sentence of an answer is a tool fact with its citations (``[1]`` markers, numbered in
order of first use). When the tools find nothing, the answer says so ("No record found")
instead of guessing. Tool output is only ever *formatted* by templates here, never
interpreted, so text inside a document ("ignore your instructions…") cannot steer it; in
LLM mode (``app.copilot.llm``) the same rule is enforced by delimiting tool output as data
and by dropping any sentence that does not cite a tool result.
"""

import logging
import re
import time
from collections.abc import Iterator
from dataclasses import asdict
from typing import Any

from sqlalchemy.orm import Session

from app.copilot import planner
from app.copilot.tools import EVENT_LABELS, Citation, Fact, ToolResult, call
from app.core.auth import CurrentUser
from app.core.config import get_settings

log = logging.getLogger(__name__)

ENGINE = "rules"


class Numbering:
    """Citation numbers in order of first use, the same source always the same number."""

    def __init__(self) -> None:
        self.items: list[Citation] = []
        self._index: dict[tuple[object, ...], int] = {}

    def marks(self, cites: list[Citation]) -> str:
        out = []
        for c in cites:
            k = c.key()
            if k not in self._index:
                self.items.append(c)
                self._index[k] = len(self.items)
            n = self._index[k]
            if f"[{n}]" not in out:
                out.append(f"[{n}]")
        return "".join(out)


def _intro(p: planner.Plan) -> str | None:
    e = p.entities
    what = EVENT_LABELS.get(e.event_type or "", "the problem")
    where = f" in the {e.formation}" if e.formation else ""
    return {
        "ledger": f"Recorded treatments for {what}{where}, ranked by how often they worked "
        "(Mitigation Ledger):",
        "handover": f"DRAFT handover note for {e.wells[0][1] if e.wells else 'this well'} "
        "(generated from the records; check and edit before sending):",
        "search": "From the reports:",
        "risk": "Offset prior risk by formation (a prior from nearby wells' history, "
        "not a prediction for this well):",
    }.get(p.intent)


_STOP_WORDS = (
    "a an and are as at be by can did do does for from had has have how i in is it its me my "
    "of on or our so that the their them there these they this to was we were what when where "
    "which who whom why will with would you your about any use used using get got tell show "
    "give find list well wells"
)
STOP = set(_STOP_WORDS.split())
WORD = re.compile(r"[a-z][a-z0-9]+")


def _stem(w: str) -> str:
    for suf in ("ings", "ing", "ies", "es", "ed", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def uncovered(question: str, ent: planner.Entities, facts: list[Fact]) -> list[str]:
    """Content words of the question that no retrieved passage contains, when fewer than
    half are covered by the best passage: the search found text *near* the question but not
    an answer to it ("who was the company man" against DDR pages that never name one)."""
    names = {w for _, n in ent.wells for w in WORD.findall(n.lower())}
    words = [w for w in WORD.findall(question.lower()) if w not in STOP and w not in names]
    stems = list(dict.fromkeys(_stem(w) for w in words))
    if not stems:
        return []
    best: set[str] = set()
    for f in facts:
        text = " ".join([f.text, *(c.text or "" for c in f.citations)]).lower()
        have = {s for s in stems if s in text}
        if len(have) > len(best):
            best = have
    if len(best) * 2 >= len(stems):
        return []
    return [s for s in stems if s not in best]


def compose(p: planner.Plan, results: list[ToolResult]) -> tuple[list[str], Numbering, bool]:
    """Sentences (with citation marks), the numbering, and whether the answer is a refusal."""
    num = Numbering()
    if p.refusal:
        return [p.refusal], num, True
    lines: list[str] = []
    if p.intent == "events" and results and results[0].data.get("count") == 0:
        # No matching events: supporting passages would only be loosely related quotes.
        results = results[:1]
    facts: list[Fact] = [f for r in results for f in r.facts]
    if not facts:
        reasons = [r.empty_reason for r in results if r.empty_reason]
        return ["No record found. " + " ".join(dict.fromkeys(reasons))], num, True
    if p.intent == "search":
        missing = uncovered(p.question, p.entities, facts)
        if missing:
            return (
                [
                    "No record found: the closest report passages do not mention "
                    + ", ".join(missing)
                    + ". Try Knowledge Search for the full list."
                ],
                num,
                True,
            )
    if intro := _intro(p):
        lines.append(intro)
    for r in results:
        for f in r.facts:
            marks = num.marks(f.citations)
            lines.append(f"{f.text} {marks}".rstrip())
        if r.empty_reason and not r.facts:
            lines.append(f"({r.empty_reason})")
    return lines, num, False


def _citation_json(n: int, c: Citation) -> dict[str, Any]:
    d = asdict(c)
    d.pop("text", None)
    return {"n": n, **d}


def _run_llm(
    session: Session, user: CurrentUser, question: str, t0: float, transport: Any
) -> list[dict[str, Any]] | None:
    """The LLM agent's answer as events, or None to fall back to the rules."""
    from app.copilot import llm

    try:
        out = llm.answer(session, user, question, transport or llm.http_transport)
    except Exception:
        log.exception("copilot LLM engine failed; answering with rules")
        return None
    if not out["lines"]:
        return None
    num: Numbering = out["numbering"]
    events: list[dict[str, Any]] = [
        {"type": "plan", "intent": "llm", "tools": [r.tool for r in out["tools"]], "entities": {}}
    ]
    events += [
        {"type": "tool", "name": r.tool, "args": r.args, "facts": len(r.facts),
         "empty": r.empty_reason, "denied": r.denied}
        for r in out["tools"]
    ]  # fmt: skip
    events += [{"type": "token", "text": line + "\n"} for line in out["lines"]]
    cited = cited_numbers(" ".join(out["lines"]))
    events.append(
        {
            "type": "citations",
            "items": [_citation_json(i + 1, c) for i, c in enumerate(num.items) if i + 1 in cited],
        }
    )
    events.append(
        {
            "type": "done",
            "refused": all(line.lower().startswith("no record") for line in out["lines"]),
            "engine": "llm",
            "intent": "llm",
            "dropped_sentences": out["dropped"],
            "took_ms": round((time.perf_counter() - t0) * 1000, 1),
            "answer": "".join(line + "\n" for line in out["lines"]),
        }
    )
    return events


def run(
    session: Session,
    user: CurrentUser,
    question: str,
    well_id: int | None = None,
    alert_id: int | None = None,
    transport: Any = None,
) -> Iterator[dict[str, Any]]:
    """The answer as a stream of events: plan, one per tool, answer tokens, citations, done."""
    t0 = time.perf_counter()
    settings = get_settings()
    if settings.copilot_engine == "llm" and (settings.llm_base_url or transport):
        events = _run_llm(session, user, question, t0, transport)
        if events is not None:
            yield from events
            return
    p = planner.plan(session, question, well_id=well_id, alert_id=alert_id)
    yield {
        "type": "plan",
        "intent": p.intent,
        "tools": [name for name, _ in p.calls],
        "entities": {
            "wells": [n for _, n in p.entities.wells],
            "formation": p.entities.formation,
            "event_type": p.entities.event_type,
            "hole_size_in": p.entities.hole_size_in,
            "radius_km": p.entities.radius_km,
        },
    }
    results: list[ToolResult] = []
    for name, args in p.calls:
        res = call(session, user, name, args)
        results.append(res)
        yield {
            "type": "tool",
            "name": name,
            "args": {k: v for k, v in res.args.items() if v is not None},
            "facts": len(res.facts),
            "empty": res.empty_reason,
            "denied": res.denied,
        }
    lines, num, refused = compose(p, results)
    for line in lines:
        yield {"type": "token", "text": line + "\n"}
    yield {
        "type": "citations",
        "items": [_citation_json(i + 1, c) for i, c in enumerate(num.items)],
    }
    yield {
        "type": "done",
        "refused": refused,
        "engine": ENGINE,
        "intent": p.intent,
        "took_ms": round((time.perf_counter() - t0) * 1000, 1),
        "answer": "".join(line + "\n" for line in lines),
    }


MARK = re.compile(r"\[(\d+)\]")


def cited_numbers(text: str) -> set[int]:
    return {int(m) for m in MARK.findall(text)}
