"""The agent loop: Claude plans, calls tools, interprets results, and answers."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import anthropic
from pydantic import BaseModel

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import TOOLS, dispatch_tool
from app.core.config import get_settings
from app.core.sessions import Session

# Safety cap on how many tool round-trips one question may take.
MAX_ITERATIONS = 12
MAX_TOKENS = 16000


class AgentEvent(BaseModel):
    """A single step surfaced to the UI as the agent works."""

    type: str  # "thinking" | "text" | "tool_use" | "tool_result" | "chart" | "final" | "error"
    text: str | None = None
    tool: str | None = None
    tool_input: dict | None = None
    is_error: bool | None = None
    artifacts: list[dict] | None = None


class AgentResult(BaseModel):
    answer: str
    events: list[AgentEvent]


def _client() -> anthropic.Anthropic:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set; the agent is disabled.")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def stream_agent(session: Session, user_message: str) -> Iterator[AgentEvent]:
    """Run one question, yielding each step as it happens (thinking, tools, answer)."""
    settings = get_settings()
    client = _client()

    session.history.append({"role": "user", "content": user_message})
    final_answer = ""

    for _ in range(MAX_ITERATIONS):
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            messages=session.history,
        )

        # Emit assistant thinking/text; keep the raw blocks in history verbatim
        # (thinking blocks must be passed back unchanged).
        assistant_text = ""
        for event in _assistant_events(response.content):
            if event.type == "text" and event.text:
                assistant_text = (assistant_text + "\n" + event.text).strip()
            yield event
        session.history.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            final_answer = assistant_text
            break

        # Execute every tool_use block and return all results in one user turn.
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            yield AgentEvent(type="tool_use", tool=block.name, tool_input=dict(block.input))
            outcome = dispatch_tool(session, block.name, dict(block.input))
            yield AgentEvent(
                type="tool_result",
                tool=block.name,
                is_error=outcome.is_error,
                text=_truncate(outcome.content_for_model),
            )
            for artifact in outcome.artifacts:
                if artifact.get("type") == "chart":
                    yield AgentEvent(type="chart", artifacts=[artifact])
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": outcome.content_for_model,
                    "is_error": outcome.is_error,
                }
            )
        session.history.append({"role": "user", "content": tool_results})
    else:
        final_answer = final_answer or "I couldn't finish within the step limit for this question."
        yield AgentEvent(type="error", text="Reached the maximum number of tool steps.")

    yield AgentEvent(type="final", text=final_answer)


def run_agent(session: Session, user_message: str) -> AgentResult:
    """Non-streaming wrapper: collect all events and return the final answer."""
    events = list(stream_agent(session, user_message))
    final = next((e.text for e in reversed(events) if e.type == "final"), "") or ""
    return AgentResult(answer=final, events=events)


def _assistant_events(content: list[Any]) -> Iterator[AgentEvent]:
    """Yield thinking/text events from an assistant message's content blocks."""
    for block in content:
        if block.type == "text":
            yield AgentEvent(type="text", text=block.text)
        elif block.type == "thinking":
            thinking = getattr(block, "thinking", "") or ""
            if thinking:
                yield AgentEvent(type="thinking", text=thinking)


def _truncate(text: str, limit: int = 2000) -> str:
    return text if len(text) <= limit else text[:limit] + "…"
