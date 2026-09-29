"""Hybrid search results: cited passages plus lessons-learned cards (S5, B2)."""

from pydantic import Field

from app.api.v1.schemas.common import EvidenceRef, ResponseModel
from app.db.vocab import EventType


class Passage(ResponseModel):
    """A retrieved chunk. ``snippet`` is plain text; ``highlights`` are ``[start, end)``
    character ranges into ``snippet`` (never HTML, so the UI can render them safely)."""

    chunk_id: int
    document_id: int
    filename: str
    doc_type: str | None
    well_id: int | None
    well_name: str | None
    synthetic: bool
    page_from: int
    page_to: int
    span_ids: list[int]
    snippet: str
    highlights: list[tuple[int, int]]
    score: float = Field(description="Fused rank score (RRF); a relevance score, not a probability")
    lexical_rank: int | None = Field(description="1-based full-text rank; null if not matched")
    dense_rank: int | None = Field(description="1-based embedding rank; null if not matched")


class LessonCard(ResponseModel):
    """Problem -> likely cause -> action taken -> outcome -> lesson for one event."""

    event_id: int
    well_id: int
    well_name: str
    synthetic: bool
    event_type: EventType
    formation: str | None
    md_m: float | None
    tvdss_m: float | None
    problem: str
    likely_cause: str | None
    action_taken: str | None
    outcome: str | None
    lesson: str | None
    confidence: float = Field(ge=0, le=1)
    verified: bool
    evidence: list[EvidenceRef]


class SearchResponse(ResponseModel):
    query: str
    passages: list[Passage]
    lessons: list[LessonCard]
    no_record_found: bool = Field(
        description="True when nothing cleared the relevance floor: the UI must say "
        "'No record found in the indexed documents' instead of showing weak matches"
    )
    embedding_provider: str = Field(description="Embedder used for the dense leg, e.g. 'hash'")
    took_ms: float
