"""In-memory session store.

A session bundles a datasource (uploaded files or a DB connection) with, later, its
conversation history. Kept deliberately simple for the MVP — swap for Redis/SQLite to
persist across restarts.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.datasources.base import DataSource
from app.datasources.duckdb_source import DuckDBSource
from app.datasources.sql_source import SQLSource


@dataclass
class Session:
    id: str
    kind: str | None = None  # "duckdb" | "sql" | None
    label: str | None = None
    datasource: DataSource | None = None
    tables: list[str] = field(default_factory=list)
    # Conversation history (Anthropic message dicts) is populated from Phase 3.
    history: list[dict] = field(default_factory=list)


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self) -> Session:
        session = Session(id=uuid.uuid4().hex)
        with self._lock:
            self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.get(session_id)

    def require(self, session_id: str) -> Session:
        session = self.get(session_id)
        if session is None:
            raise KeyError(session_id)
        return session

    # ── datasource attachment ────────────────────────────────────────────
    def attach_duckdb(self, session: Session) -> DuckDBSource:
        """Ensure the session has a DuckDB datasource and return it."""
        if isinstance(session.datasource, DuckDBSource):
            return session.datasource
        settings = get_settings()
        db_path = settings.sessions_dir / f"{session.id}.duckdb"
        source = DuckDBSource(db_path)
        session.datasource = source
        session.kind = "duckdb"
        session.label = "Uploaded files"
        return source

    def attach_sql(self, session: Session, connection_url: str, label: str | None) -> SQLSource:
        source = SQLSource(connection_url)
        source.test_connection()
        self._close_datasource(session)
        session.datasource = source
        session.kind = "sql"
        session.label = label or source.dialect
        session.tables = [t.name for t in source.get_schema(sample_rows=0).tables]
        return source

    def _close_datasource(self, session: Session) -> None:
        if session.datasource is not None:
            try:
                session.datasource.close()
            except Exception:
                pass
            session.datasource = None

    def delete(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session:
            self._close_datasource(session)


session_manager = SessionManager()
