"""Skeleton routes for the knowledge layer: documents, review queue, events, search, ledger.

Paths and parameters follow master plan §8. Each handler raises NotImplementedYetError with
the backend phase that will implement it (docs/BACKEND_PLAN.md §6).
"""

from typing import Annotated

from fastapi import APIRouter, Query, UploadFile

from app.core.errors import NOT_IMPLEMENTED, NotImplementedYetError

router = APIRouter(responses=NOT_IMPLEMENTED)


@router.post("/documents", tags=["documents"], summary="Upload report files and start ingestion")
def upload_documents(files: list[UploadFile]) -> None:
    raise NotImplementedYetError("Document upload & ingestion (S1)", "B1")


@router.get("/documents/{document_id}", tags=["documents"], summary="Document metadata and status")
def get_document(document_id: int) -> None:
    raise NotImplementedYetError("Document metadata (S1)", "B1")


@router.get(
    "/documents/{document_id}/pages/{page_no}",
    tags=["documents"],
    summary="Page image and text spans for evidence highlighting",
)
def get_page(document_id: int, page_no: int) -> None:
    raise NotImplementedYetError("Page evidence view (S1)", "B1")


@router.get("/review-queue", tags=["review"], summary="Low-confidence extractions awaiting review")
def list_review_queue() -> None:
    raise NotImplementedYetError("Review queue (S2)", "B2")


@router.post("/review-queue/{item_id}", tags=["review"], summary="Accept, correct or reject")
def review_item(item_id: int) -> None:
    raise NotImplementedYetError("Review decision (S2)", "B2")


@router.get("/events", tags=["events"], summary="Search drilling events")
def list_events(
    event_type: str | None = None,
    formation: str | None = None,
    well_id: int | None = None,
    radius_km: Annotated[float | None, Query(gt=0, le=100)] = None,
    tvdss_from_m: float | None = None,
    tvdss_to_m: float | None = None,
) -> None:
    raise NotImplementedYetError("Event search (S2/S5)", "B2")


@router.get("/search", tags=["search"], summary="Hybrid document search")
def search(q: Annotated[str, Query(min_length=1, max_length=500)]) -> None:
    raise NotImplementedYetError("Hybrid search (S5)", "B2")


@router.get("/ledger", tags=["ledger"], summary="Mitigation effectiveness ranking (USP 2)")
def ledger(event_type: str, formation: str | None = None, basin: str | None = None) -> None:
    raise NotImplementedYetError("Mitigation Effectiveness Ledger (S8)", "B3")
