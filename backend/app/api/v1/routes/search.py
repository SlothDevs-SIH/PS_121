"""Hybrid document search with lessons-learned cards (S5, B2)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.params import NOT_FOUND, RadiusKm, check_range, require_well_for_radius
from app.api.v1.schemas.search import SearchResponse
from app.db.session import get_session
from app.db.vocab import EventType
from app.search.hybrid import SearchQuery, run

router = APIRouter(tags=["search"])
DbSession = Annotated[Session, Depends(get_session)]

MAX_SEARCH_LIMIT = 50


@router.get(
    "/search",
    summary="Hybrid document search",
    response_model=SearchResponse,
    responses=NOT_FOUND,
)
def search(
    session: DbSession,
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
    return run(
        session,
        SearchQuery(
            q=q.strip(),
            well_id=well_id,
            radius_km=radius_km,
            formation=formation,
            event_types=tuple(event_type or ()),
            doc_type=doc_type,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        ),
    )
