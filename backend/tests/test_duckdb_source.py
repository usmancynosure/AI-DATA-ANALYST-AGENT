import pandas as pd
import pytest

from app.datasources.duckdb_source import DuckDBSource, sanitize_table_name
from app.datasources.sql_guard import UnsafeQueryError


@pytest.fixture
def csv_file(tmp_path):
    df = pd.DataFrame(
        {
            "region": ["North", "South", "North", "West"],
            "amount": [100, 250, 175, 300],
            "date": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
        }
    )
    path = tmp_path / "Sales 2024.csv"
    df.to_csv(path, index=False)
    return path


@pytest.fixture
def source(tmp_path):
    src = DuckDBSource(tmp_path / "session.duckdb")
    yield src
    src.close()


def test_sanitize_table_name():
    assert sanitize_table_name("Sales 2024.csv") == "sales_2024"
    assert sanitize_table_name("123data.csv") == "t_123data"
    assert sanitize_table_name("weird!!name.xlsx") == "weird_name"


def test_ingest_and_schema(source, csv_file):
    table = source.ingest_file(csv_file)
    assert table == "sales_2024"

    schema = source.get_schema()
    assert schema.dialect == "duckdb"
    assert len(schema.tables) == 1
    t = schema.tables[0]
    assert t.name == "sales_2024"
    assert t.row_count == 4
    assert {c.name for c in t.columns} == {"region", "amount", "date"}
    assert len(t.sample_rows) == 3


def test_run_sql_aggregation(source, csv_file):
    source.ingest_file(csv_file)
    result = source.run_sql(
        "SELECT region, SUM(amount) AS total FROM sales_2024 GROUP BY region ORDER BY total DESC",
        max_rows=100,
        timeout_seconds=10,
    )
    assert result.columns == ["region", "total"]
    assert result.row_count == 3
    assert result.rows[0] == ["West", 300]  # highest total first
    assert ["North", 275] in result.rows
    assert result.truncated is False


def test_run_sql_truncation(source, csv_file):
    source.ingest_file(csv_file)
    result = source.run_sql("SELECT * FROM sales_2024", max_rows=2, timeout_seconds=10)
    assert result.row_count == 2
    assert result.truncated is True


def test_run_sql_rejects_writes(source, csv_file):
    source.ingest_file(csv_file)
    with pytest.raises(UnsafeQueryError):
        source.run_sql("DROP TABLE sales_2024", max_rows=10, timeout_seconds=10)


def test_duplicate_table_names_get_suffixed(source, csv_file):
    t1 = source.ingest_file(csv_file)
    t2 = source.ingest_file(csv_file)
    assert t1 == "sales_2024"
    assert t2 == "sales_2024_2"
