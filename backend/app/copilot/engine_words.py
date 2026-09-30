"""Question words: stop words, the word pattern and a light stemmer, shared by the
answer-coverage check (engine) and the scope check (scope)."""

import re

_STOP_WORDS = (
    "a an and are as at be by can did do does for from had has have how i in is it its me my "
    "of on or our so that the their them there these they this to was we were what when where "
    "which who whom why will with would you your about any use used using get got tell show "
    "give find list well wells"
)
STOP = set(_STOP_WORDS.split())
WORD = re.compile(r"[a-z][a-z0-9]+")


def stem(w: str) -> str:
    for suf in ("ings", "ing", "ies", "es", "ed", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w
