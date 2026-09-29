"""S5 pure pieces: hash embedder, snippets/highlights, lesson-card template."""

import math
from datetime import date

from app.db.models import Event, Mitigation
from app.db.models.documents import EMBEDDING_DIM
from app.search import hybrid, lessons
from app.search.embed import HashEmbedder


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_hash_embedder_is_deterministic_and_normalised() -> None:
    e = HashEmbedder()
    v1, v2 = e.embed(["Pipe stuck in Barail", "Pipe stuck in Barail"])
    assert v1 == v2 and len(v1) == EMBEDDING_DIM
    assert math.isclose(math.sqrt(sum(x * x for x in v1)), 1.0, rel_tol=1e-4)
    assert e.name == "hash:v1"


def test_hash_embedder_synonyms_bring_related_text_closer() -> None:
    e = HashEmbedder()
    q, related, unrelated = e.embed(
        ["lost returns", "severe losses while drilling", "rig move and safety meeting"]
    )
    assert _cos(q, related) > _cos(q, unrelated) + 0.1


def test_highlights_are_ranges_into_the_snippet() -> None:
    text = "Pipe stuck (differential) at 3,136 m in Barail. Spotted pipe-freeing pill."
    hl = hybrid.highlight(text, ["pipe", "stuck", "barail"])
    assert [text[a:b] for a, b in hl] == ["Pipe", "stuck", "Barail", "pipe"]


def test_long_chunk_snippet_windows_on_first_hit() -> None:
    full = "x " * 400 + "Lost circulation at 2,783 m in Tipam. " + "y " * 400
    snippet, hl = hybrid.make_snippet(full, ["circul"])
    assert snippet.startswith("… ") and snippet.endswith(" …")
    assert len(snippet) <= hybrid.SNIPPET_CHARS + 4
    assert [snippet[a:b] for a, b in hl] == ["circulation"]


def _event(outcomes: list[str]) -> Event:
    ev = Event(
        event_type="STUCK",
        subtype="differential",
        md_m=3552.0,
        params={"overpull_kn": 560.5},
        hole_size_in=8.5,
        mw_sg=1.43,
        npt_hours=28.9,
        event_date=date(2009, 1, 27),
    )
    texts = ["Worked pipe", "Spotted pipe release pill", "Backed off and fished"]
    ev.mitigations = [
        Mitigation(seq=k + 1, action_code="X", action_text=texts[k], outcome=o)
        for k, o in enumerate(outcomes)
    ]
    return ev


def test_lesson_card_after_failed_attempts() -> None:
    card = lessons.build(_event(["fail", "fail", "success"]), "Barail")
    assert card["problem"].startswith("Stuck pipe (differential) at 3552 m MD in Barail")
    assert "overpull 560 kN" in card["problem"]
    assert card["likely_cause"] == "Differential sticking, as stated in the report"
    assert card["action_taken"].startswith("1. Worked pipe (fail)")
    assert card["outcome"] == "Resolved by 'Backed off and fished' on attempt 3 of 3; 28.9 h NPT."
    assert "consider trying it earlier" in card["lesson"]
    assert "check the ledger" in card["lesson"]  # a card never claims a success rate
    assert card["generated_by"] == lessons.TEMPLATE_VERSION


def test_lesson_card_unresolved_and_empty() -> None:
    card = lessons.build(_event(["fail", "fail"]), None)
    assert card["outcome"].startswith("Not resolved")
    assert card["lesson"].startswith("None of the recorded actions")
    bare = lessons.build(_event([]), None)
    assert bare["action_taken"] is None and bare["outcome"] is None and bare["lesson"] is None
