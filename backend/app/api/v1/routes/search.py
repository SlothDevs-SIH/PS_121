"""Hybrid document search with lessons-learned cards (S5, B2)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.v1.params import RadiusKm, check_range, require_well_for_radius
from app.api.v1.schemas.search import SearchResponse
from app.core.errors import NOT_IMPLEMENTED, NotImplementedYetError
from app.db.vocab import EventType

router = APIRouter(tags=["search"], responses=NOT_IMPLEMENTED)

MAX_SEARCH_LIMIT = 50


@router.get("/search", summary="Hybrid document search", response_model=SearchResponse)
def search(
    q: Annotated[str, Query(min_length=1, max_length=500)],
    well_id: int | None = None,
    radius_km: RadiusKm = None,
    formation: Annotated[str | None, Query(max_length=100)] = None,
    event_type: Annotated[
        list[EventType] | None, Query(description="Repeat to match any of several types")
    ] = None,
    doc_type: Annotated[str | None, Query(max_length=20)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_SEARCH_LIMIT)] = 10,
) -> SearchResponse:
    """Full-text (tsvector) and dense (pgvector) retrieval fused with RRF (k = 60) after the
    filters are applied; returns cited passages and the lesson cards of matching events.
    ``no_record_found`` is true when nothing clears the relevance floor."""
    require_well_for_radius(well_id, radius_km)
    check_range("date_from", date_from, "date_to", date_to)
    raise NotImplementedYetError("Hybrid search (S5)", "B2")
