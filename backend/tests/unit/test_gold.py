"""Gold set from review decisions (Part 7, V-B15): gold values and the score."""

from app.db.models.engineering import ReviewItem
from app.extract.gold import changed_fields, gold_values, score


def _item(status: str, proposed: dict, correction: dict | None = None) -> ReviewItem:
    return ReviewItem(kind="casing", status=status, proposed=proposed, correction=correction)


def test_gold_values_follow_the_verdict() -> None:
    p = {"od_in": None, "shoe_md_m": 3900}
    assert gold_values(_item("accepted", p)) == p
    assert gold_values(_item("corrected", p, {"od_in": 9.625})) == {
        "od_in": 9.625,
        "shoe_md_m": 3900,
    }
    assert gold_values(_item("rejected", p)) is None
    assert changed_fields(p, {"od_in": 9.625, "shoe_md_m": 3900}) == ["od_in"]


def test_score_by_kind_band_and_field() -> None:
    rows = [
        {
            "verdict": "accepted",
            "kind": "event",
            "confidence": 0.7,
            "changed_fields": [],
            "synthetic": True,
        },
        {
            "verdict": "corrected",
            "kind": "casing",
            "confidence": 0.4,
            "changed_fields": ["od_in"],
            "synthetic": True,
        },
        {
            "verdict": "corrected",
            "kind": "casing",
            "confidence": 0.45,
            "changed_fields": ["od_in", "toc_md_m"],
            "synthetic": False,
        },
        {
            "verdict": "rejected",
            "kind": "event",
            "confidence": 0.3,
            "changed_fields": [],
            "synthetic": False,
        },
    ]
    s = score(rows)
    assert s["items"] == {
        "n": 4,
        "accepted": 1,
        "corrected": 2,
        "rejected": 1,
        "right_as_proposed": 0.25,
    }
    assert s["by_kind"]["casing"]["corrected"] == 2
    assert (
        s["by_confidence"]["0.00-0.50"]["n"] == 3
        and s["by_confidence"]["0.50-0.75"]["accepted"] == 1
    )
    assert s["most_corrected_fields"] == {"od_in": 2, "toc_md_m": 1}
    assert s["synthetic_share"] == 0.5
    assert score([])["items"]["n"] == 0
