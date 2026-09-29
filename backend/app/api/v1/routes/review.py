"""Review queue: low-confidence extractions awaiting a human decision (S2, B2)."""

from typing import Annotated

from fastapi import APIRouter, Body, Query

from app.api.v1.params import NOT_FOUND, Cursor, Limit
from app.api.v1.schemas.review import ReviewDecision, ReviewItem, ReviewPage
from app.core.errors import NOT_IMPLEMENTED, NotImplementedYetError
from app.db.vocab import ReviewKind, ReviewStatus

router = APIRouter(tags=["review"], responses=NOT_IMPLEMENTED)


@router.get(
    "/review-queue",
    summary="Low-confidence extractions awaiting review",
    response_model=ReviewPage,
)
def list_review_queue(
    status_: Annotated[
        ReviewStatus | None, Query(alias="status", description="Default: pending only")
    ] = "pending",
    kind: ReviewKind | None = None,
    document_id: int | None = None,
    limit: Limit = 50,
    cursor: Cursor = None,
) -> ReviewPage:
    """Items ordered by confidence (lowest first), then id. Pass ``status`` explicitly to
    see decided items; ``status_counts`` always covers every status."""
    raise NotImplementedYetError("Review queue (S2)", "B2")


@router.post(
    "/review-queue/{item_id}",
    summary="Accept, correct or reject",
    response_model=ReviewItem,
    responses=NOT_FOUND,
)
def review_item(item_id: int, decision: Annotated[ReviewDecision, Body()]) -> ReviewItem:
    """Applies the decision to the target record (verified / corrected / rejected), records
    ``decided_by``/``decided_at`` and returns the updated item. 409 if already decided."""
    raise NotImplementedYetError("Review decision (S2)", "B2")
