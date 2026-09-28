"""Well-name normalisation and alias resolution (master plan §Stage 3).

Reports spell the same well many ways ("SYN-ASM-07", "SYN ASM 07", "SYNASM#7"). Exact
matches on a normalised key resolve automatically; near matches become AliasCandidate rows
for a human to confirm — they are never merged silently.
"""

import re

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import AliasCandidate, Well

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")
_LEADING_ZEROS = re.compile(r"(?<![0-9])0+(?=[0-9])")
SIMILARITY_FLOOR = 0.45


def normalise_name(raw: str) -> str:
    """Upper-case, drop punctuation and spaces, strip leading zeros: SYN-ASM-07 → SYNASM7."""
    key = _NON_ALNUM.sub("", raw.upper())
    return _LEADING_ZEROS.sub("", key)


def resolve_well(session: Session, raw_name: str, document_id: int | None = None) -> Well | None:
    key = normalise_name(raw_name)
    if not key:
        return None
    for well in session.scalars(select(Well)):
        if key in {normalise_name(n) for n in (well.canonical_name, *well.aliases)}:
            if raw_name not in well.aliases and raw_name != well.canonical_name:
                well.aliases = [*well.aliases, raw_name]
            return well
    best = session.execute(
        text(
            "SELECT id, similarity(canonical_name, :raw) AS sim FROM well ORDER BY sim DESC LIMIT 1"
        ),
        {"raw": raw_name},
    ).first()
    if best is not None and best.sim >= SIMILARITY_FLOOR:
        session.add(
            AliasCandidate(
                raw_name=raw_name,
                well_id=best.id,
                similarity=float(best.sim),
                document_id=document_id,
            )
        )
    return None
