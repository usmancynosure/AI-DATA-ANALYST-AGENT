"""DuckDB-backed datasource for uploaded CSV/Excel files.

Every uploaded file becomes a table in a per-session DuckDB database. This gives the
agent one uniform SQL interface regardless of whether the data came from a file or a
database, and DuckDB's analytical engine handles large files efficiently.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path

import duckdb

from .base import ColumnInfo, DataSource, QueryResult, SchemaInfo, TableInfo
from .sql_guard import ensure_read_only

_SAFE_IDENT = re.compile(r"[^A-Za-z0-9_]")


def sanitize_table_name(raw: str) -> str:
    """Turn a filename into a safe SQL identifier (e.g. 'Sales 2024.csv' -> 'sales_2024')."""
    stem = Path(raw).stem.lower()
    name = _SAFE_IDENT.sub("_", stem)
    name = re.sub(r"_+", "_", name).strip("_")
    if not name:
        name = "table"
    if name[0].isdigit():
        name = f"t_{name}"
    return name


class DuckDBSource(DataSource):
    dialect = "duckdb"

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._con = duckdb.connect(str(db_path))
        self._lock = threading.Lock()

    # ── ingestion ────────────────────────────────────────────────────────
    def ingest_file(self, file_path: Path, table_name: str | None = None) -> str:
        """Load a CSV or Excel file as a table. Returns the created table name."""
        table = table_name or sanitize_table_name(file_path.name)
        table = self._unique_table_name(table)
        suffix = file_path.suffix.lower()

        with self._lock:
            if suffix in (".csv", ".tsv", ".txt"):
                self._con.execute(
                    f'CREATE TABLE "{table}" AS '
                    "SELECT * FROM read_csv_auto(?, sample_size=-1)",
                    [str(file_path)],
                )
            elif suffix in (".xlsx", ".xls"):
                df = self._read_excel(file_path)  # noqa: F841  (referenced by DuckDB)
                self._con.execute(f'CREATE TABLE "{table}" AS SELECT * FROM df')
            else:
                raise ValueError(f"Unsupported file type: {suffix}")
        return table

    @staticmethod
    def _read_excel(file_path: Path):
        import pandas as pd

        return pd.read_excel(file_path)

    def _existing_tables(self) -> set[str]:
        rows = self._con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
        return {r[0] for r in rows}

    def _unique_table_name(self, base: str) -> str:
        existing = self._existing_tables()
        if base not in existing:
            return base
        i = 2
        while f"{base}_{i}" in existing:
            i += 1
        return f"{base}_{i}"

    # ── schema ───────────────────────────────────────────────────────────
    def get_schema(self, sample_rows: int = 3) -> SchemaInfo:
        with self._lock:
            tables: list[TableInfo] = []
            for table in sorted(self._existing_tables()):
                cols = self._con.execute(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = 'main' AND table_name = ? ORDER BY ordinal_position",
                    [table],
                ).fetchall()
                columns = [ColumnInfo(name=c[0], type=str(c[1])) for c in cols]

                row_count = self._con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]

                samples: list[dict] = []
                if sample_rows > 0:
                    rel = self._con.execute(f'SELECT * FROM "{table}" LIMIT {int(sample_rows)}')
                    names = [d[0] for d in rel.description]
                    for row in rel.fetchall():
                        samples.append({n: _json_safe(v) for n, v in zip(names, row, strict=False)})

                tables.append(
                    TableInfo(
                        name=table,
                        columns=columns,
                        row_count=row_count,
                        sample_rows=samples,
                    )
                )
        return SchemaInfo(dialect=self.dialect, tables=tables)

    # ── query ────────────────────────────────────────────────────────────
    def run_sql(self, query: str, max_rows: int, timeout_seconds: int) -> QueryResult:
        statement = ensure_read_only(query)

        with self._lock:
            timer = threading.Timer(timeout_seconds, self._con.interrupt)
            timer.start()
            start = time.perf_counter()
            try:
                rel = self._con.execute(statement)
                names = [d[0] for d in rel.description]
                # Fetch one extra row to detect truncation.
                fetched = rel.fetchmany(max_rows + 1)
            except duckdb.InterruptException as exc:  # pragma: no cover - timing dependent
                raise TimeoutError(
                    f"Query exceeded the {timeout_seconds}s time limit."
                ) from exc
            finally:
                timer.cancel()
            elapsed_ms = (time.perf_counter() - start) * 1000

        truncated = len(fetched) > max_rows
        rows = fetched[:max_rows]
        return QueryResult(
            columns=names,
            rows=[[_json_safe(v) for v in row] for row in rows],
            row_count=len(rows),
            truncated=truncated,
            elapsed_ms=round(elapsed_ms, 2),
        )

    def close(self) -> None:
        with self._lock:
            self._con.close()


def _json_safe(value):
    """Convert DuckDB/py values into JSON-serializable primitives."""
    import datetime
    import decimal

    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return str(value)
