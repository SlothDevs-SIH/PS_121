"""Shared API building blocks: evidence references and the trust fields every extracted fact
carries (master plan principle P1, "no citation, no claim"; BACKEND_PLAN section 3.1)."""

from pydantic import BaseModel, ConfigDict, Field


class ResponseModel(BaseModel):
    """Base for response bodies: fields with defaults are still *required* in the OpenAPI
    output schema (the server always sends them), so the generated TypeScript has no
    spurious optional properties."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class EvidenceRef(ResponseModel):
    """Where a fact was read: page ``page_no`` (1-based) of ``document_id``, highlighting the
    ``span_ids`` (GET /documents/{document_id}/pages/{page_no} returns their boxes)."""

    document_id: int
    page_no: int
    span_ids: list[int]
    filename: str | None = None
    doc_type: str | None = None


class EvidenceRefIn(BaseModel):
    """Evidence supplied by a client (manual event entry, review correction)."""

    model_config = ConfigDict(extra="forbid")

    document_id: int
    page_no: int = Field(ge=1)
    span_ids: list[int] = Field(default_factory=list, max_length=200)


class Extracted(ResponseModel):
    """Trust fields of an extracted record. ``verified=false`` values are shown dashed."""

    confidence: float = Field(ge=0, le=1)
    verified: bool
    evidence: list[EvidenceRef]


class ExcludedWell(ResponseModel):
    """A well left out of a result, with the reason (never dropped silently)."""

    well_id: int
    name: str
    reason: str
