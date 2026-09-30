"""Gold set from the review queue (Part 7, V-B15).

Every decided review item is a labelled example of the extractor at work, with the page
lines it read:

- **accepted**: the extraction was right; the gold values are what was proposed;
- **corrected**: it was wrong; the gold values are the proposal with the reviewer's
  correction applied, and the changed fields say where the extractor erred;
- **rejected**: nothing should have been extracted (a false positive); no gold values.

Exported as JSON lines (one item per line), these become the evaluation set that master
plan §13.1 calls for, built from real reports as soon as engineers review them. The score
reports how often low-confidence extractions were right, and which fields were corrected
most: honest numbers about the extractor on whatever the reviewers saw.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, TextSpan
from app.db.models.engineering import ReviewItem

DECIDED = ("accepted", "corrected", "rejected")
CONFIDENCE_BANDS = ((0.0, 0.5), (0.5, 0.75), (0.75, 1.01))


def gold_values(item: ReviewItem) -> dict[str, Any] | None:
    if item.status == "rejected":
        return None
    if item.status == "corrected":
        return {**(item.proposed or {}), **(item.correction or {})}
    return dict(item.proposed or {})


def changed_fields(proposed: dict[str, Any], correction: dict[str, Any] | None) -> list[str]:
    return sorted(k for k, v in (correction or {}).items() if proposed.get(k) != v)


def export(session: Session) -> list[dict[str, Any]]:
    """Decided review items as gold rows, oldest decision first."""
    items = list(
        session.scalars(
            select(ReviewItem)
            .where(ReviewItem.status.in_(DECIDED))
            .order_by(ReviewItem.decided_at, ReviewItem.id)
        )
    )
    docs = {
        d.id: d
        for d in session.scalars(
            select(Document).where(Document.id.in_({i.document_id for i in items} - {None}))
        )
    }
    span_ids = {s for i in items for s in (i.span_ids or [])}
    lines = {
        sid: text
        for sid, text in session.execute(
            select(TextSpan.id, TextSpan.text).where(TextSpan.id.in_(span_ids or {-1}))
        )
    }
    rows = []
    for i in items:
        d = docs.get(i.document_id) if i.document_id else None
        rows.append(
            {
                "review_item_id": i.id,
                "kind": i.kind,
                "field": i.field,
                "verdict": i.status,
                "confidence": i.confidence,
                "reason": i.reason,
                "document_id": i.document_id,
                "filename": d.filename if d else None,
                "doc_type": d.doc_type if d else None,
                "synthetic": d.synthetic if d else None,
                "page_no": i.page_no,
                "source_lines": [lines[s] for s in (i.span_ids or []) if s in lines],
                "proposed": i.proposed or {},
                "gold": gold_values(i),
                "changed_fields": changed_fields(i.proposed or {}, i.correction)
                if i.status == "corrected"
                else [],
                "decided_by": i.decided_by,
                "decided_at": i.decided_at.isoformat() if i.decided_at else None,
            }
        )
    return rows


@dataclass
class _Tally:
    n: int = 0
    accepted: int = 0
    corrected: int = 0
    rejected: int = 0

    def add(self, verdict: str) -> None:
        self.n += 1
        setattr(self, verdict, getattr(self, verdict) + 1)

    def out(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "accepted": self.accepted,
            "corrected": self.corrected,
            "rejected": self.rejected,
            "right_as_proposed": round(self.accepted / self.n, 3) if self.n else None,
        }


def score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """How often queued extractions were right, by kind and by confidence band, and which
    fields reviewers corrected most. Only covers what went to review (low confidence)."""
    overall = _Tally()
    by_kind: dict[str, _Tally] = defaultdict(_Tally)
    by_band: dict[str, _Tally] = defaultdict(_Tally)
    fields: Counter[str] = Counter()
    for r in rows:
        overall.add(r["verdict"])
        by_kind[r["kind"]].add(r["verdict"])
        c = r["confidence"] or 0.0
        band = next(f"{lo:.2f}-{min(hi, 1.0):.2f}" for lo, hi in CONFIDENCE_BANDS if lo <= c < hi)
        by_band[band].add(r["verdict"])
        fields.update(r["changed_fields"])
    return {
        "items": overall.out(),
        "by_kind": {k: t.out() for k, t in sorted(by_kind.items())},
        "by_confidence": {b: t.out() for b, t in sorted(by_band.items())},
        "most_corrected_fields": dict(fields.most_common(10)),
        "synthetic_share": round(sum(bool(r["synthetic"]) for r in rows) / len(rows), 3)
        if rows
        else None,
        "note": "Covers only extractions that went to review (below the confidence "
        "threshold); confident extractions are not in this sample.",
    }
