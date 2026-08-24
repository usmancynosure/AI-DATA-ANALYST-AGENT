"""Agent-loop tests with a mocked Claude client (no network, no Docker)."""

from types import SimpleNamespace

import pandas as pd
import pytest

from app.agent import orchestrator
from app.core.sessions import SessionManager


def _block(**kwargs):
    return SimpleNamespace(**kwargs)


class FakeMessages:
    def __init__(self, scripted):
        self._scripted = scripted
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._scripted[len(self.calls) - 1]


class FakeClient:
    def __init__(self, scripted):
        self.messages = FakeMessages(scripted)


@pytest.fixture
def session_with_data(tmp_path):
    df = pd.DataFrame({"region": ["N", "S", "N", "W"], "amount": [10, 20, 30, 40]})
    csv = tmp_path / "sales.csv"
    df.to_csv(csv, index=False)

    manager = SessionManager()
    session = manager.create()
    # Point DuckDB at a temp file for this test.
    from app.datasources.duckdb_source import DuckDBSource

    source = DuckDBSource(tmp_path / "s.duckdb")
    source.ingest_file(csv, table_name="sales")
    session.datasource = source
    session.kind = "duckdb"
    yield session
    source.close()


def test_agent_runs_tools_and_answers(session_with_data, monkeypatch):
    # Scripted 3-turn conversation: get_schema -> run_sql -> final answer.
    scripted = [
        _block(
            stop_reason="tool_use",
            content=[
                _block(type="text", text="Let me inspect the schema."),
                _block(type="tool_use", id="t1", name="get_schema", input={}),
            ],
        ),
        _block(
            stop_reason="tool_use",
            content=[
                _block(type="tool_use", id="t2", name="run_sql",
                       input={"query": "SELECT SUM(amount) AS total FROM sales"}),
            ],
        ),
        _block(
            stop_reason="end_turn",
            content=[_block(type="text", text="The total amount is 100.")],
        ),
    ]
    monkeypatch.setattr(orchestrator, "_client", lambda: FakeClient(scripted))

    result = orchestrator.run_agent(session_with_data, "What is the total amount?")

    assert result.answer == "The total amount is 100."
    tool_uses = [e for e in result.events if e.type == "tool_use"]
    assert [e.tool for e in tool_uses] == ["get_schema", "run_sql"]

    # The run_sql tool_result must have carried the computed total back.
    sql_results = [e for e in result.events if e.type == "tool_result" and e.tool == "run_sql"]
    assert sql_results and "100" in sql_results[0].text
    assert not sql_results[0].is_error
    assert result.events[-1].type == "final"


def test_agent_stops_and_reports_unsafe_sql(session_with_data, monkeypatch):
    scripted = [
        _block(
            stop_reason="tool_use",
            content=[
                _block(type="tool_use", id="t1", name="run_sql",
                       input={"query": "DROP TABLE sales"}),
            ],
        ),
        _block(
            stop_reason="end_turn",
            content=[_block(type="text", text="I can only run read-only queries.")],
        ),
    ]
    monkeypatch.setattr(orchestrator, "_client", lambda: FakeClient(scripted))

    result = orchestrator.run_agent(session_with_data, "delete the sales table")

    err = [e for e in result.events if e.type == "tool_result" and e.is_error]
    assert err, "unsafe SQL should produce an error tool_result"
    assert result.answer == "I can only run read-only queries."
