"""Agent-loop tests with a mocked Gemini client (no network, no Docker)."""

from types import SimpleNamespace

import pandas as pd
import pytest
from google.genai import types

from app.agent import orchestrator


def _model_turn(parts, finish_reason="STOP"):
    """A fake generate_content response carrying one model Content."""
    content = types.Content(role="model", parts=parts)
    candidate = SimpleNamespace(content=content, finish_reason=finish_reason)
    return SimpleNamespace(candidates=[candidate])


def _text(text):
    return types.Part(text=text)


def _call(name, args):
    return types.Part(function_call=types.FunctionCall(name=name, args=args))


class FakeModels:
    def __init__(self, scripted):
        self._scripted = scripted
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self._scripted[len(self.calls) - 1]


class FakeClient:
    def __init__(self, scripted):
        self.models = FakeModels(scripted)


@pytest.fixture
def session_with_data(tmp_path):
    df = pd.DataFrame({"region": ["N", "S", "N", "W"], "amount": [10, 20, 30, 40]})
    csv = tmp_path / "sales.csv"
    df.to_csv(csv, index=False)

    from app.core.sessions import SessionManager
    from app.datasources.duckdb_source import DuckDBSource

    manager = SessionManager()
    session = manager.create()
    source = DuckDBSource(tmp_path / "s.duckdb")
    source.ingest_file(csv, table_name="sales")
    session.datasource = source
    session.kind = "duckdb"
    yield session
    source.close()


def test_agent_runs_tools_and_answers(session_with_data, monkeypatch):
    # Scripted 3-turn conversation: get_schema -> run_sql -> final answer.
    scripted = [
        _model_turn([_text("Let me inspect the schema."), _call("get_schema", {})]),
        _model_turn([_call("run_sql", {"query": "SELECT SUM(amount) AS total FROM sales"})]),
        _model_turn([_text("The total amount is 100.")]),
    ]
    monkeypatch.setattr(orchestrator, "_client", lambda: FakeClient(scripted))

    result = orchestrator.run_agent(session_with_data, "What is the total amount?")

    assert result.answer == "The total amount is 100."
    tool_uses = [e for e in result.events if e.type == "tool_use"]
    assert [e.tool for e in tool_uses] == ["get_schema", "run_sql"]

    sql_results = [e for e in result.events if e.type == "tool_result" and e.tool == "run_sql"]
    assert sql_results and "100" in sql_results[0].text
    assert not sql_results[0].is_error
    assert result.events[-1].type == "final"


def test_agent_reports_unsafe_sql(session_with_data, monkeypatch):
    scripted = [
        _model_turn([_call("run_sql", {"query": "DROP TABLE sales"})]),
        _model_turn([_text("I can only run read-only queries.")]),
    ]
    monkeypatch.setattr(orchestrator, "_client", lambda: FakeClient(scripted))

    result = orchestrator.run_agent(session_with_data, "delete the sales table")

    err = [e for e in result.events if e.type == "tool_result" and e.is_error]
    assert err, "unsafe SQL should produce an error tool_result"
    assert result.answer == "I can only run read-only queries."
