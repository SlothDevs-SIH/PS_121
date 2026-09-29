"""Copilot (S10, B5): questions in, cited answers out."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.common import ResponseModel


class CopilotAsk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=1000)
    well_id: int | None = Field(None, description="The well on screen ('this well')")
    alert_id: int | None = Field(None, description="The alert on screen ('this alert')")


class CopilotCitation(ResponseModel):
    n: int = Field(description="The [n] marker in the answer")
    kind: str = Field(description="page (a report page) or record (a database row)")
    label: str
    document_id: int | None
    page_no: int | None
    span_ids: list[int]
    filename: str | None
    record_type: str | None = Field(description="event | well | alert | ledger | risk")
    record_id: int | None


class CopilotToolCall(ResponseModel):
    name: str
    args: dict[str, Any]
    facts: int
    empty: str | None
    denied: bool


class CopilotAnswer(ResponseModel):
    """The whole answer at once (``?stream=false``). The SSE stream sends the same pieces as
    events: ``plan``, ``tool`` (one per call), ``token`` (one per line), ``citations``,
    ``done``."""

    answer: str
    citations: list[CopilotCitation]
    intent: str
    tools: list[CopilotToolCall]
    refused: bool = Field(description="No record found, outside the records, or not allowed")
    engine: str = Field(description="rules (deterministic planner) or llm")
    took_ms: float
