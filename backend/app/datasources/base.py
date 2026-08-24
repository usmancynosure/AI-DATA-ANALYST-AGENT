"""Datasource abstraction shared by uploaded-file (DuckDB) and external SQL sources."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class ColumnInfo(BaseModel):
    name: str
    type: str


class TableInfo(BaseModel):
    name: str
    columns: list[ColumnInfo]
    row_count: int | None = None
    sample_rows: list[dict] = []


class SchemaInfo(BaseModel):
    """The structure of a datasource, given to the agent so it can write correct SQL."""

    dialect: str  # "duckdb" | "postgresql" | "mysql"
    tables: list[TableInfo]

    def to_prompt(self) -> str:
        """Compact, LLM-friendly rendering of the schema."""
        lines = [f"SQL dialect: {self.dialect}", ""]
        for t in self.tables:
            cols = ", ".join(f"{c.name} {c.type}" for c in t.columns)
            count = f" (~{t.row_count} rows)" if t.row_count is not None else ""
            lines.append(f"Table {t.name}{count}:")
            lines.append(f"  {cols}")
        return "\n".join(lines)


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool = False
    elapsed_ms: float | None = None

    def to_records(self) -> list[dict]:
        return [dict(zip(self.columns, r, strict=False)) for r in self.rows]


class DataSource(ABC):
    """A queryable source of tabular data."""

    dialect: str

    @abstractmethod
    def get_schema(self, sample_rows: int = 3) -> SchemaInfo: ...

    @abstractmethod
    def run_sql(self, query: str, max_rows: int, timeout_seconds: int) -> QueryResult: ...

    def close(self) -> None:  # pragma: no cover - optional override
        pass
