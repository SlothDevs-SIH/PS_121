"""Is the question about something the records contain at all? (Part 7, V-B34)

Retrieval always returns *something*, and every tool can summarise a well, so a question
about a fact the records never hold ("the daily mud cost", "the wind speed during the rig
move") used to get a confident answer about something else. This check looks at the
question's **focus**, the noun phrase it asks for ("what was the <focus> …", "which
<focus> …", "how many <focus> …", "who …"), and refuses when a focus word appears nowhere
in the indexed reports and is not a known entity (well, formation, problem type).

Only the focus counts: an incidental verb the reports never use ("to *cure* losses") does
not make a question unanswerable, but an asked-for quantity they never record does.
"""

import re
import time
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.copilot.engine_words import STOP, WORD, stem
from app.copilot.tools import EVENT_LABELS
from app.db.models import Chunk, Formation

# Question heads that say "tell me about …" rather than name a recorded quantity.
GENERIC = frozenset(
    stem(w)
    for w in [
        "happened",
        "happen",
        "worked",
        "work",
        "works",
        "problems",
        "problem",
        "issues",
        "issue",
        "risks",
        "risk",
        "treatments",
        "treatment",
        "mitigations",
        "mitigation",
        "actions",
        "action",
        "lessons",
        "lesson",
        "history",
        "events",
        "event",
        "reports",
        "report",
        "records",
        "record",
        "wells",
        "well",
        "offsets",
        "offset",
        "alerts",
        "alert",
        "causes",
        "cause",
        "options",
        "option",
        "steps",
        "step",
        "things",
        "thing",
        "went",
        "kind",
        "type",
        "types",
        "sort",
    ]
)
# Heads that point at the words after "of" ("the name of the supervisor").
PASS_THROUGH = frozenset({"name", "names", "type", "kind", "number", "amount", "brand", "list"})
FOCUS = re.compile(
    r"^\s*(?:what|which|who|whom|whose|how\s+many|how\s+much)\b"
    r"(?:\s+(?:was|were|is|are|did|does|do|has|had))?"
    r"(?:\s+(?:the|a|an))?\s*(?P<focus>[^?]*)",
    re.I,
)
BOUNDARY = re.compile(
    r"\b(?:on|in|for|at|during|to|from|by|that|did|does|was|were|is|are|used|use|ran|run|"
    r"had|has|have|when|where|while|after|before|with|within|near|between|into|per)\b",
    re.I,
)
TTL_S = 600.0

_cache: tuple[float, tuple[int, int], frozenset[str]] | None = None


def focus_words(question: str) -> list[str]:
    """The asked-for noun phrase's words (lower case), or [] when the question has no
    what/which/how-many/who head (then nothing is checked)."""
    m = FOCUS.match(question)
    if not m:
        return []
    rest = m.group("focus")
    b = BOUNDARY.search(rest)
    head = rest[: b.start()] if b else rest
    words = WORD.findall(head.lower())
    if words and words[0] in PASS_THROUGH:
        # "the name of the supervisor": the focus is what comes after "of".
        tail = re.search(r"\bof\s+(?:the\s+|a\s+|an\s+)?([^?]*)", rest, re.I)
        if tail:
            after = tail.group(1)
            b2 = BOUNDARY.search(after)
            words = WORD.findall((after[: b2.start()] if b2 else after).lower())
    words = [w for w in words if w not in STOP]
    if words and stem(words[0]) in GENERIC:
        # "which reports mention …", "what problems occurred …": the question asks for
        # records themselves; what follows is a verb, not a recorded quantity.
        return []
    return words


def _terms(texts: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for t in texts:
        out.update(stem(w) for w in WORD.findall(t.lower()))
    return out


def corpus_terms(session: Session, now: float | None = None) -> frozenset[str]:
    """Stems of every word in the indexed reports, plus problem labels and formation names.
    Cached for ``TTL_S``, and rebuilt early when chunks are added or removed."""
    global _cache
    now = time.monotonic() if now is None else now
    n, top = session.execute(
        select(func.count(Chunk.id), func.coalesce(func.max(Chunk.id), 0))
    ).one()
    key = (int(n), int(top))
    if _cache and _cache[1] == key and now - _cache[0] < TTL_S:
        return _cache[2]
    terms = _terms(session.scalars(select(Chunk.text)))
    terms |= _terms(EVENT_LABELS.values())
    for name, syns in session.execute(select(Formation.name, Formation.synonyms)):
        terms |= _terms([name, *(syns or [])])
    frozen = frozenset(terms)
    _cache = (now, key, frozen)
    return frozen


def off_record(question: str, known: frozenset[str], entity_words: set[str]) -> list[str]:
    """Focus words the records never mention (empty: the question is in scope)."""
    out = []
    for w in focus_words(question):
        s = stem(w)
        if s in GENERIC or w in entity_words or s in known or w.isdigit():
            continue
        out.append(w)
    return out
