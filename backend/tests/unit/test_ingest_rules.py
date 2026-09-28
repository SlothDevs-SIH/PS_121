from datetime import date

import pytest

from app.ingest.chunking import chunk_lines
from app.ingest.classify import classify, find_report_date, find_well_name, is_synthetic
from app.normalise.aliases import normalise_name


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("DAILY DRILLING REPORT\nWell: X", "DDR"),
        ("DAILY  DRlLLING REPORT", "OTHER"),  # OCR garble falls through to review, not a wrong type
        ("WELL COMPLETION REPORT", "WCR"),
        ("Cementing Job Report", "CEMENT_REPORT"),
        ("Casing tally for 9-5/8 in", "CASING_REPORT"),
        ("minutes of meeting", "OTHER"),
    ],
)
def test_classify(text: str, expected: str) -> None:
    assert classify(text) == expected


@pytest.mark.parametrize(
    ("line", "name"),
    [
        ("Well: SYN-ASM-05    Rig: Rig SYN-5    Report No: 2", "SYN-ASM-05"),
        ("Well: SYN ASM 02_ Rig: Rig SYN-4_ Report No: 2", "SYN ASM 02"),  # OCR artefacts
        ("Well: SYNASM#7", "SYNASM#7"),
        ("Well Name: HPJ-12  Field: X", "HPJ-12"),
        ("No well here", None),
    ],
)
def test_find_well_name(line: str, name: str | None) -> None:
    assert find_well_name(line) == name


def test_report_dates() -> None:
    ddr = "Well: A Rig: R Report No: 2 Date: 2012-01-07"
    assert find_report_date(ddr, "DDR") == date(2012, 1, 7)
    wcr = "Spud date: 2009-01-09    Completion date: 2009-02-15"
    assert find_report_date(wcr, "WCR") == date(2009, 2, 15)
    assert find_report_date("Spud date: 2009-01-09", "DDR") is None  # not a report date
    assert find_report_date("Date: 15/02/2009") == date(2009, 2, 15)
    assert find_report_date("Date: 31/02/2009") is None


def test_synthetic_watermark() -> None:
    assert is_synthetic("SYNTHETIC DATA - NOT OIL INDIA DATA")
    assert not is_synthetic("Daily drilling report")


@pytest.mark.parametrize(
    ("raw", "key"),
    [
        ("SYN-ASM-07", "SYNASM7"),
        ("SYN ASM 07", "SYNASM7"),
        ("SYNASM#7", "SYNASM7"),
        ("syn-asm-10", "SYNASM10"),
    ],
)
def test_normalise_name(raw: str, key: str) -> None:
    assert normalise_name(raw) == key


def _table(n: int) -> list[tuple[int, int, str]]:
    return [
        (1, 10 + i, f"00:{i:02d}  01:00  1.0  2000  DRL  row {i} " + "x" * 60) for i in range(n)
    ]


def test_chunking_keeps_tables_together_and_titles_with_text() -> None:
    head = [(1, 1, "DAILY DRILLING REPORT"), (1, 2, "SYNTHETIC DATA"), (1, 3, "Well: A Rig: B")]
    tail = [(2, 100, "REMARKS"), (2, 101, "Normal drilling.")]
    chunks = chunk_lines(head + _table(14) + tail)  # ~1.4k chars of table: over the soft limit
    assert chunks[0].text.startswith("DAILY DRILLING REPORT\nSYNTHETIC DATA\nWell: A")
    assert len([c for c in chunks if "row 0 " in c.text or "row 13 " in c.text]) == 1
    assert chunks[-1].text == "REMARKS\nNormal drilling."
    assert chunks[-1].page_from == 2
    assert [sid for c in chunks for sid in c.span_ids] == [1, 2, 3, *range(10, 24), 100, 101]


def test_chunking_hard_limit_splits_oversized_tables() -> None:
    chunks = chunk_lines(_table(40))
    assert len(chunks) >= 2
    assert all(len(c.text) <= 1800 + 120 for c in chunks)
