"""Chat endpoint that runs the agent for a session (non-streaming)."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent.orchestrator import (
    AgentEvent,
    AgentResult,
    friendly_error,
    run_agent,
    stream_agent,
)
from app.core.sessions import Session, session_manager

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str


def _require_ready_session(session_id: str) -> Session:
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session.datasource is None:
        raise HTTPException(status_code=400, detail="Attach data to this session first.")
    return session


@router.post("/sessions/{session_id}/chat", response_model=AgentResult)
def chat(session_id: str, req: ChatRequest) -> AgentResult:
    session = _require_ready_session(session_id)
    try:
        return run_agent(session, req.message)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _sse(event: AgentEvent) -> str:
    return f"data: {event.model_dump_json()}\n\n"


@router.post("/sessions/{session_id}/chat/stream")
def chat_stream(session_id: str, req: ChatRequest) -> StreamingResponse:
    """Stream agent steps as Server-Sent Events (consume with fetch/ReadableStream)."""
    session = _require_ready_session(session_id)

    def generate():
        try:
            for event in stream_agent(session, req.message):
                yield _sse(event)
        except RuntimeError as exc:
            yield _sse(AgentEvent(type="error", text=str(exc)))
        except Exception as exc:  # surface unexpected failures to the client
            yield _sse(AgentEvent(type="error", text=friendly_error(exc)))
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
