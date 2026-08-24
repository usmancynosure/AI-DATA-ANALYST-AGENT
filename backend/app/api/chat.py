"""Chat endpoint that runs the agent for a session (non-streaming)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agent.orchestrator import AgentResult, run_agent
from app.core.sessions import session_manager

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str


@router.post("/sessions/{session_id}/chat", response_model=AgentResult)
def chat(session_id: str, req: ChatRequest) -> AgentResult:
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session.datasource is None:
        raise HTTPException(status_code=400, detail="Attach data to this session first.")
    try:
        return run_agent(session, req.message)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
