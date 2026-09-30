"""The copilot's scope check (Part 7, V-B34): a question's focus must be something the
reports mention; incidental words and record-type heads do not count."""

import pytest

from app.copilot.engine_words import stem
from app.copilot.scope import focus_words, off_record

KNOWN = frozenset(
    stem(w)
    for w in ["rig", "mud", "drill", "bit", "losses", "lcm", "cement", "plug", "pipe", "stuck"]
)


@pytest.mark.parametrize(
    ("q", "focus"),
    [
        ("What was the daily mud cost on SYN-ASM-08?", ["daily", "mud", "cost"]),
        ("Which hospital treated injuries on SYN-ASM-19?", ["hospital", "treated", "injuries"]),
        ("How many litres of diesel did the rig burn?", ["litres", "diesel"]),
        ("What was the name of the drilling supervisor on SYN-ASM-14?", ["drilling", "supervisor"]),
        ("Who was the company man on SYN-ASM-05?", ["company", "man"]),
        # Record-type heads ask for the records themselves: nothing to check.
        ("Which reports mention a pipe release pill?", []),
        ("What problems occurred in the 12 1/4 inch section?", []),
        ("Which wells used a cement plug to cure losses?", []),
        # No what/which/how-many/who head: nothing to check.
        ("Show reports where detergent was pumped", []),
        ("Where was jarring needed to free stuck pipe?", []),
    ],
)
def test_focus_is_the_asked_for_noun_phrase(q: str, focus: list[str]) -> None:
    assert focus_words(q) == focus


def test_off_record_names_only_focus_words_the_reports_never_use() -> None:
    assert off_record("What was the daily mud cost on SYN-ASM-08?", KNOWN, set()) == [
        "daily",
        "cost",
    ]
    assert off_record("What drill bit was run?", KNOWN, set()) == []
    # Entity words (a formation the planner recognised) never count as unknown.
    assert off_record("Which Barail intervals had losses?", KNOWN, {"barail"}) == ["intervals"]
    assert off_record("How many 2024 losses?", KNOWN, set()) == []
