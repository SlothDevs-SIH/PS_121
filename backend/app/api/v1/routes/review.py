"""Review queue: low-confidence extractions awaiting a human decision (S2, B2)."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.params import CONFLICT, NOT_FOUND, Cursor, Limit
from app.api.v1.schemas.review import ReviewDecision, ReviewItem, ReviewPage
from app.core.auth import CurrentUser, get_current_user
from app.db.session import get_session
from app.db.vocab import ReviewKind, ReviewStatus
from app.extract import review_service

router = APIRouter(tags=["review"])
DbSession = Annotated[Session, Depends(get_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]


@router.get(
    "/review-queue",
    summary="Low-confidence extractions awaiting review",
    response_model=ReviewPage,
)
def list_review_queue(
    session: DbSession,
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
    return review_service.list_items(
        session, status=status_, kind=kind, document_id=document_id, limit=limit, cursor=cursor
    )


@router.post(
    "/review-queue/{item_id}",
    summary="Accept, correct or reject",
    response_model=ReviewItem,
    responses={**NOT_FOUND, **CONFLICT},
)
def review_item(
    item_id: int, decision: Annotated[ReviewDecision, Body()], session: DbSession, user: User
) -> ReviewItem:
    """Applies the decision to the target record (verified / corrected / rejected), records
    ``decided_by``/``decided_at`` and returns the updated item. 409 if already decided."""
    item = review_service.decide(session, item_id, decision, user.user_id)
    session.commit()
    return item
