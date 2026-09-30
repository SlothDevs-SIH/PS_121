"""Copilot (S10, B5): ``POST /api/v1/copilot/chat``, streamed as server-sent events."""

import json
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.v1.schemas.copilot import CopilotAnswer, CopilotAsk
from app.copilot.engine import run
from app.core import ratelimit
from app.core.audit import audit
from app.core.auth import CurrentUser, require
from app.core.config import get_settings
from app.db.session import session_scope

router = APIRouter(tags=["copilot"])
User = Annotated[CurrentUser, Depends(require("copilot"))]


def _events(user: CurrentUser, body: CopilotAsk) -> Iterator[dict[str, Any]]:
    # Its own session: a streamed response outlives the request's dependencies.
    with session_scope() as session:
        done: dict[str, Any] = {}
        for ev in run(session, user, body.message, well_id=body.well_id, alert_id=body.alert_id):
            if ev["type"] == "done":
                done = ev
            yield ev
        audit(
            session,
            user,
            "copilot_query",
            "copilot",
            None,
            question=body.message,
            intent=done.get("intent"),
            refused=done.get("refused"),
            engine=done.get("engine"),
        )


def _sse(events: Iterator[dict[str, Any]]) -> Iterator[str]:
    for ev in events:
        yield f"event: {ev['type']}\ndata: {json.dumps(ev, default=str)}\n\n"


@router.post(
    "/copilot/chat",
    summary="Ask the copilot (SSE stream; ?stream=false for one JSON answer)",
    response_model=CopilotAnswer,
    responses={
        200: {"content": {"text/event-stream": {}}},
        429: {"description": "Too many questions this minute"},
    },
)
def copilot_chat(
    body: Annotated[CopilotAsk, Body()],
    user: User,
    stream: Annotated[bool, Query(description="false: one JSON answer instead of SSE")] = True,
) -> Any:
    """Answers only from the read-only tools (search, events, offsets, risk profile, ledger,
    well summary, alert explanation) the user's role allows. Every line cites a report page
    or a database record as ``[n]``; when nothing is found the answer says so. Audited, and
    limited to ``copilot_rate_per_minute`` questions per user (429 with Retry-After)."""
    ratelimit.hit(f"copilot:{user.user_id}", get_settings().copilot_rate_per_minute)
    if stream:
        return StreamingResponse(
            _sse(_events(user, body)),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    tools: list[dict[str, Any]] = []
    out: dict[str, Any] = {}
    for ev in _events(user, body):
        if ev["type"] == "tool":
            tools.append({k: ev[k] for k in ("name", "args", "facts", "empty", "denied")})
        elif ev["type"] == "citations":
            out["citations"] = ev["items"]
        elif ev["type"] == "done":
            out.update(ev)
    return CopilotAnswer(
        answer=out["answer"],
        citations=out.get("citations", []),
        intent=out["intent"],
        tools=tools,
        refused=out["refused"],
        engine=out["engine"],
        took_ms=out["took_ms"],
    )
