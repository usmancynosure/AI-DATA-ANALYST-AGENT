"""Tool definitions (provider-neutral JSON schema) and server-side dispatch."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.core.sessions import Session
from app.datasources.sql_guard import UnsafeQueryError
from app.sandbox.runner import DockerSandbox, SandboxError

# Rows sent back to the model are capped to keep the context small; the UI receives
# the full (already row-limited) result as an artifact.
_MODEL_ROW_CAP = 50

TOOLS = [
    {
        "name": "get_schema",
        "description": (
            "Return the tables in the connected dataset with their columns, types, and "
            "a few sample rows. Call this before writing SQL if you don't know the schema."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "run_sql",
        "description": (
            "Execute a single read-only SELECT/WITH query against the connected dataset "
            "and return the resulting rows. Write operations are rejected."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "A single read-only SQL query."}
            },
            "required": ["query"],
        },
    },
    {
        "name": "run_python",
        "description": (
            "Run Python (pandas, numpy, scikit-learn, matplotlib) in a secure sandbox. "
            "Use `data_queries` to load data as pandas DataFrames — each query result is "
            "a DataFrame named by `name` (a single one is also available as `df`). Assign "
            "to a variable named `result` to return a value. Open matplotlib figures are "
            "captured and shown to the user automatically."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python source to execute."},
                "data_queries": {
                    "type": "array",
                    "description": "SQL results to load into the sandbox as DataFrames.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Variable name for the DataFrame.",
                            },
                            "sql": {
                                "type": "string",
                                "description": "Read-only SQL producing the DataFrame.",
                            },
                        },
                        "required": ["name", "sql"],
                    },
                },
            },
            "required": ["code"],
        },
    },
]


@dataclass
class ToolOutcome:
    """Result of running one tool: text for the model plus artifacts for the UI."""

    content_for_model: str
    is_error: bool = False
    artifacts: list[dict] = field(default_factory=list)


def dispatch_tool(session: Session, name: str, tool_input: dict) -> ToolOutcome:
    if session.datasource is None:
        return ToolOutcome("Error: no dataset is attached to this session.", is_error=True)
    try:
        if name == "get_schema":
            return _get_schema(session)
        if name == "run_sql":
            return _run_sql(session, tool_input["query"])
        if name == "run_python":
            return _run_python(session, tool_input["code"], tool_input.get("data_queries") or [])
        return ToolOutcome(f"Error: unknown tool '{name}'.", is_error=True)
    except Exception as exc:  # defensive: never let a tool crash the loop
        return ToolOutcome(f"Error running {name}: {exc}", is_error=True)


def _get_schema(session: Session) -> ToolOutcome:
    schema = session.datasource.get_schema()
    return ToolOutcome(
        content_for_model=schema.to_prompt(),
        artifacts=[{"type": "schema", "schema": schema.model_dump()}],
    )


def _query(session: Session, sql: str):
    settings = get_settings()
    return session.datasource.run_sql(
        sql,
        max_rows=settings.max_query_rows,
        timeout_seconds=settings.query_timeout_seconds,
    )


def _run_sql(session: Session, query: str) -> ToolOutcome:
    try:
        result = _query(session, query)
    except UnsafeQueryError as exc:
        return ToolOutcome(f"Rejected: {exc}", is_error=True)
    except TimeoutError as exc:
        return ToolOutcome(f"Query timed out: {exc}", is_error=True)
    except Exception as exc:
        return ToolOutcome(f"SQL error: {exc}", is_error=True)

    preview = result.rows[:_MODEL_ROW_CAP]
    payload = {
        "columns": result.columns,
        "rows": preview,
        "row_count": result.row_count,
        "shown_to_you": len(preview),
        "truncated": result.truncated,
    }
    note = ""
    if len(preview) < result.row_count:
        note = f"\n(Showing first {len(preview)} of {result.row_count} rows.)"
    if result.truncated:
        note += "\n(Result was truncated at the row limit.)"

    return ToolOutcome(
        content_for_model=json.dumps(payload) + note,
        artifacts=[
            {
                "type": "table",
                "query": query,
                "columns": result.columns,
                "rows": result.rows,
                "row_count": result.row_count,
                "truncated": result.truncated,
            }
        ],
    )


def _run_python(session: Session, code: str, data_queries: list[dict]) -> ToolOutcome:
    # Materialize each requested query as a DataFrame payload for the sandbox.
    dataframes: dict[str, dict] = {}
    for spec in data_queries:
        var_name, sql = spec["name"], spec["sql"]
        try:
            result = _query(session, sql)
        except UnsafeQueryError as exc:
            return ToolOutcome(f"data_queries['{var_name}'] rejected: {exc}", is_error=True)
        except Exception as exc:
            return ToolOutcome(f"data_queries['{var_name}'] failed: {exc}", is_error=True)
        dataframes[var_name] = {"columns": result.columns, "rows": result.rows}

    sandbox = DockerSandbox()
    try:
        run = sandbox.run(code, dataframes=dataframes or None)
    except SandboxError as exc:
        return ToolOutcome(f"Sandbox unavailable: {exc}", is_error=True)

    # Text back to the model: stdout, result, error — but NOT image bytes (too large).
    parts: list[str] = []
    if run.stdout:
        parts.append("stdout:\n" + run.stdout.strip())
    if run.result is not None:
        parts.append("result:\n" + json.dumps(run.result)[:4000])
    if run.images:
        parts.append(f"[{len(run.images)} chart(s) generated and shown to the user]")
    if run.error:
        parts.append("error:\n" + run.error.strip())
    if not parts:
        parts.append("(code ran with no output)")

    artifacts: list[dict] = [{"type": "chart", "image": img} for img in run.images]

    return ToolOutcome(
        content_for_model="\n\n".join(parts),
        is_error=not run.ok,
        artifacts=artifacts,
    )
