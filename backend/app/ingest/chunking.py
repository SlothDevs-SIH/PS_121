"""Section-aware chunking of page lines for search (S5).

A new chunk starts at a section heading or once a chunk is long; a chunk never ends in
the middle of a table (consecutive lines with column gaps), unless it hits the hard cap.
"""

import re
from dataclasses import dataclass

SOFT_LIMIT = 1000
MIN_CHUNK = 80  # stacked headings/titles stay with the text that follows them
HARD_LIMIT = 1800
_HEADING = re.compile(r"^(\d+\.\s+)?[A-Z][A-Z0-9 &/\-]{2,48}$")


@dataclass
class ChunkDraft:
    page_from: int
    page_to: int
    span_ids: list[int]
    text: str


def _is_table_row(text: str) -> bool:
    return text.count("  ") >= 2


def chunk_lines(lines: list[tuple[int, int, str]]) -> list[ChunkDraft]:
    """`lines` are (page_no, span_id, text) in reading order."""
    chunks: list[ChunkDraft] = []
    cur: list[tuple[int, int, str]] = []
    size = 0

    def flush() -> None:
        nonlocal cur, size
        if cur:
            chunks.append(
                ChunkDraft(cur[0][0], cur[-1][0], [c[1] for c in cur], "\n".join(c[2] for c in cur))
            )
        cur, size = [], 0

    for page_no, span_id, text in lines:
        heading = bool(_HEADING.match(text.strip())) and not _is_table_row(text)
        in_table = bool(cur) and _is_table_row(cur[-1][2]) and _is_table_row(text)
        if cur and (
            (heading and size >= MIN_CHUNK)
            or (size > SOFT_LIMIT and not in_table)
            or size > HARD_LIMIT
        ):
            flush()
        cur.append((page_no, span_id, text))
        size += len(text) + 1
    flush()
    return chunks
