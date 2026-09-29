"""Skeleton route for the Mitigation Effectiveness Ledger (S8, USP 2), built in B3.

The B2 knowledge-layer routes moved to their own modules: events.py, review.py, search.py
and correlation.py. The handler raises NotImplementedYetError with its backend phase
(docs/BACKEND_PLAN.md section 6).
"""

from fastapi import APIRouter

from app.core.errors import NOT_IMPLEMENTED, NotImplementedYetError

router = APIRouter(responses=NOT_IMPLEMENTED)


@router.get("/ledger", tags=["ledger"], summary="Mitigation effectiveness ranking (USP 2)")
def ledger(event_type: str, formation: str | None = None, basin: str | None = None) -> None:
    raise NotImplementedYetError("Mitigation Effectiveness Ledger (S8)", "B3")
