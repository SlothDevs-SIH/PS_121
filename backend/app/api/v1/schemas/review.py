"""Review queue: low-confidence extractions a human accepts, corrects or rejects (S2, B2)."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.api.v1.schemas.common import EvidenceRef, ResponseModel
from app.db.vocab import ReviewKind, ReviewStatus


class ReviewItem(ResponseModel):
    id: int
    kind: ReviewKind
    target_id: int | None = Field(description="Row id in the table named by kind, if written")
    document_id: int | None
    filename: str | None
    doc_type: str | None
    well_id: int | None
    well_name: str | None
    page_no: int | None
    span_ids: list[int]
    evidence: list[EvidenceRef]
    field: str | None = Field(description="Field under review; null = the whole record")
    reason: str = Field(description="Why it needs review, e.g. 'confidence 0.62 < 0.75'")
    confidence: float = Field(ge=0, le=1)
    proposed: dict[str, JsonValue] = Field(description="Extracted values, canonical units")
    status: ReviewStatus
    decided_by: str | None
    decided_at: datetime | None
    correction: dict[str, JsonValue] | None
    created_at: datetime


class ReviewPage(ResponseModel):
    items: list[ReviewItem]
    next_cursor: str | None
    status_counts: dict[str, int] = Field(description="Items per status (all kinds)")


class ReviewAccept(BaseModel):
    """The proposed values are right: the target becomes verified."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["accept"]
    note: str | None = Field(default=None, max_length=2000)


class ReviewCorrect(BaseModel):
    """Replace some proposed values (same keys and canonical units as ``proposed``); the
    target is updated and verified, and the pair is kept for the evaluation gold set."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["correct"]
    fields: dict[str, JsonValue] = Field(min_length=1)
    note: str | None = Field(default=None, max_length=2000)


class ReviewReject(BaseModel):
    """Not a real fact: the target is rejected (events get status 'rejected')."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["reject"]
    reason: str = Field(min_length=1, max_length=2000)


ReviewDecision = Annotated[
    ReviewAccept | ReviewCorrect | ReviewReject, Field(discriminator="action")
]
