"""External SQL datasource (PostgreSQL / MySQL) via SQLAlchemy.

Connections are opened read-only where the dialect supports it, and every query is
still passed through the read-only guard. Prefer pointing this at a database user that
only has SELECT privileges — that is the strongest guarantee.
"""

from __future__ import annotations

import time

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url

from .base import ColumnInfo, DataSource, QueryResult, SchemaInfo, TableInfo
from .sql_guard import ensure_read_only

# Map a user-facing scheme to a SQLAlchemy driver URL.
_DRIVER_MAP = {
    "postgres": "postgresql+psycopg",
    "postgresql": "postgresql+psycopg",
    "mysql": "mysql+pymysql",
    "mariadb": "mysql+pymysql",
}


def normalize_url(raw_url: str) -> str:
    url = make_url(raw_url)
    backend = url.get_backend_name()
    driver = _DRIVER_MAP.get(backend)
    if driver is None:
        raise ValueError(
            f"Unsupported database '{backend}'. Supported: postgres, mysql/mariadb."
        )
    return url.set(drivername=driver).render_as_string(hide_password=False)


class SQLSource(DataSource):
    def __init__(self, connection_url: str):
        self._url = normalize_url(connection_url)
        self._backend = make_url(self._url).get_backend_name()
        self.dialect = "postgresql" if "postgres" in self._backend else "mysql"
        self._engine: Engine = create_engine(
            self._url,
            pool_pre_ping=True,
            connect_args=self._connect_args(),
        )

    def _connect_args(self) -> dict:
        if self.dialect == "postgresql":
            # Read-only session + a hard statement timeout as defense in depth.
            return {"options": "-c default_transaction_read_only=on"}
        return {}

    def test_connection(self) -> None:
        with self._engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    # ── schema ───────────────────────────────────────────────────────────
    def get_schema(self, sample_rows: int = 3) -> SchemaInfo:
        inspector = inspect(self._engine)
        default_schema = inspector.default_schema_name
        tables: list[TableInfo] = []

        with self._engine.connect() as conn:
            for table_name in inspector.get_table_names(schema=default_schema):
                cols = inspector.get_columns(table_name, schema=default_schema)
                columns = [ColumnInfo(name=c["name"], type=str(c["type"])) for c in cols]

                samples: list[dict] = []
                if sample_rows > 0:
                    quoted = self._quote(table_name)
                    rows = conn.execute(
                        text(f"SELECT * FROM {quoted} LIMIT :n"), {"n": sample_rows}
                    )
                    names = list(rows.keys())
                    for row in rows.fetchall():
                        samples.append(
                            {n: _json_safe(v) for n, v in zip(names, row, strict=False)}
                        )

                tables.append(
                    TableInfo(name=table_name, columns=columns, sample_rows=samples)
                )
        return SchemaInfo(dialect=self.dialect, tables=tables)

    def _quote(self, identifier: str) -> str:
        if self.dialect == "mysql":
            return f"`{identifier}`"
        return f'"{identifier}"'

    # ── query ────────────────────────────────────────────────────────────
    def run_sql(self, query: str, max_rows: int, timeout_seconds: int) -> QueryResult:
        statement = ensure_read_only(query)
        start = time.perf_counter()

        with self._engine.connect() as conn:
            self._apply_timeout(conn, timeout_seconds)
            result = conn.execute(text(statement))
            names = list(result.keys())
            fetched = result.fetchmany(max_rows + 1)

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

    def _apply_timeout(self, conn, timeout_seconds: int) -> None:
        ms = int(timeout_seconds * 1000)
        try:
            if self.dialect == "postgresql":
                conn.execute(text(f"SET statement_timeout = {ms}"))
            elif self.dialect == "mysql":
                conn.execute(text(f"SET SESSION max_execution_time = {ms}"))
        except Exception:  # pragma: no cover - not all servers support it
            pass

    def close(self) -> None:
        self._engine.dispose()


def _json_safe(value):
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
