"""The agent loop: Gemini plans, calls tools, interprets results, and answers."""

from __future__ import annotations

import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import TOOLS, dispatch_tool
from app.core.config import get_settings
from app.core.sessions import Session

# Safety cap on how many tool round-trips one question may take.
MAX_ITERATIONS = 12
# Transient server errors (5xx / high demand) are retried with backoff.
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 2.0
# Hard wall-clock cap per model call (client-side). google-genai's HttpOptions.timeout
# is only a *server-side deadline* and does not abort a stalled/queued request, so we
# run each call in a worker thread and give up on it after this many seconds. This
# guarantees the agent surfaces an error instead of hanging forever.
HARD_CALL_TIMEOUT_SECONDS = 75
_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="gemini")


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


# Server-side request deadline (ms). Below ~8s the API rejects it; this bounds how long
# the server holds a request. The hard client-side cap (above) is the real backstop.
REQUEST_TIMEOUT_MS = 60_000


def _client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set; the agent is disabled.")
    return genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    )


def _gemini_config() -> types.GenerateContentConfig:
    declarations = [
        types.FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters_json_schema=t["parameters"],
        )
        for t in TOOLS
    ]
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=declarations)],
        # We drive the tool loop ourselves; don't let the SDK auto-execute.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        # Surface the model's reasoning summaries as "thinking" events.
        thinking_config=types.ThinkingConfig(include_thoughts=True),
    )


def stream_agent(session: Session, user_message: str) -> Iterator[AgentEvent]:
    """Run one question, yielding each step as it happens (thinking, tools, answer)."""
    settings = get_settings()
    client = _client()
    config = _gemini_config()

    session.history.append(
        types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
    )
    final_answer = ""

    for _ in range(MAX_ITERATIONS):
        response = _generate_with_retry(client, settings.gemini_model, session.history, config)

        candidate = response.candidates[0] if response.candidates else None
        content = candidate.content if candidate else None
        parts = (content.parts if content and content.parts else []) or []

        # Emit thinking/text; keep the model turn in history verbatim.
        assistant_text = ""
        function_calls = []
        for part in parts:
            if getattr(part, "function_call", None):
                function_calls.append(part.function_call)
            elif getattr(part, "text", None):
                if getattr(part, "thought", False):
                    yield AgentEvent(type="thinking", text=part.text)
                else:
                    assistant_text = (assistant_text + "\n" + part.text).strip()
                    yield AgentEvent(type="text", text=part.text)

        if content is not None:
            session.history.append(content)

        if not function_calls:
            final_answer = assistant_text or _finish_reason_message(candidate)
            break

        # Execute every function call and return all results in one turn.
        response_parts = []
        for fc in function_calls:
            args = dict(fc.args or {})
            yield AgentEvent(type="tool_use", tool=fc.name, tool_input=args)
            outcome = dispatch_tool(session, fc.name, args)
            yield AgentEvent(
                type="tool_result",
                tool=fc.name,
                is_error=outcome.is_error,
                text=_truncate(outcome.content_for_model),
            )
            for artifact in outcome.artifacts:
                if artifact.get("type") == "chart":
                    yield AgentEvent(type="chart", artifacts=[artifact])
            response_parts.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": outcome.content_for_model, "is_error": outcome.is_error},
                )
            )
        session.history.append(types.Content(role="user", parts=response_parts))
    else:
        final_answer = final_answer or "I couldn't finish within the step limit for this question."
        yield AgentEvent(type="error", text="Reached the maximum number of tool steps.")

    yield AgentEvent(type="final", text=final_answer)


def run_agent(session: Session, user_message: str) -> AgentResult:
    """Non-streaming wrapper: collect all events and return the final answer."""
    events = list(stream_agent(session, user_message))
    final = next((e.text for e in reversed(events) if e.type == "final"), "") or ""
    return AgentResult(answer=final, events=events)


_RETRYABLE_CODES = {429, 500, 502, 503, 504}


def _generate_with_retry(client, model, contents, config):
    """Call generate_content, retrying transient overload/5xx/429 errors with backoff."""
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        future = _EXECUTOR.submit(
            client.models.generate_content, model=model, contents=contents, config=config
        )
        try:
            return future.result(timeout=HARD_CALL_TIMEOUT_SECONDS)
        except FuturesTimeout:
            future.cancel()  # the underlying request may keep running, but we stop waiting
            last_exc = TimeoutError(
                f"The model did not respond within {HARD_CALL_TIMEOUT_SECONDS}s "
                "(the API may be overloaded or rate-limited)."
            )
        except errors.APIError as exc:
            if getattr(exc, "code", None) not in _RETRYABLE_CODES:
                raise
            last_exc = exc
        except httpx.RequestError as exc:
            # Transient transport failure (server disconnect, connect/read timeout).
            last_exc = exc
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
    raise last_exc  # type: ignore[misc]


def friendly_error(exc: Exception) -> str:
    """Turn a provider exception into a short, human-readable message for the UI."""
    if isinstance(exc, TimeoutError):
        return str(exc)
    code = getattr(exc, "code", None)
    if code == 429:
        return (
            "Gemini rate limit / quota reached (common on the free tier). "
            "Wait a minute and retry, switch GEMINI_MODEL to a lighter model "
            "(e.g. gemini-flash-lite-latest), or enable billing on your API key."
        )
    if code in (500, 502, 503, 504):
        return "Gemini is temporarily overloaded. Please retry in a few seconds."
    return f"Agent failed: {exc}"


def _finish_reason_message(candidate) -> str:
    """Fallback text when the model stops with no visible answer (e.g. safety block)."""
    reason = getattr(candidate, "finish_reason", None) if candidate else None
    if reason and str(reason) not in ("FinishReason.STOP", "STOP"):
        return f"The model stopped without an answer (reason: {reason})."
    return "The model returned no answer."


def _truncate(text: str, limit: int = 2000) -> str:
    return text if len(text) <= limit else text[:limit] + "…"
