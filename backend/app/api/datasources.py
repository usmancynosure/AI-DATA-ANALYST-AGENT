"""Endpoints for creating sessions and attaching data (uploads or DB connections)."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.schemas import (
    ConnectRequest,
    QueryRequest,
    QueryResponse,
    SessionResponse,
    UploadResponse,
)
from app.core.config import get_settings
from app.core.sessions import Session, session_manager
from app.datasources.duckdb_source import sanitize_table_name
from app.datasources.sql_guard import UnsafeQueryError

router = APIRouter(tags=["datasources"])

_ALLOWED_SUFFIXES = {".csv", ".tsv", ".txt", ".xlsx", ".xls"}


def _require_session(session_id: str) -> Session:
    try:
        return session_manager.require(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.") from None


@router.post("/sessions", response_model=SessionResponse)
def create_session() -> SessionResponse:
    session = session_manager.create()
    return SessionResponse(session_id=session.id)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str) -> SessionResponse:
    session = _require_session(session_id)
    return SessionResponse(
        session_id=session.id,
        kind=session.kind,
        label=session.label,
        tables=session.tables,
    )


@router.post("/sessions/{session_id}/upload", response_model=UploadResponse)
async def upload_file(session_id: str, file: UploadFile = File(...)) -> UploadResponse:
    session = _require_session(session_id)
    settings = get_settings()

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(_ALLOWED_SUFFIXES)}",
        )

    dest = settings.uploads_dir / f"{session.id}__{Path(file.filename).name}"
    try:
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
    finally:
        await file.close()

    source = session_manager.attach_duckdb(session)
    # Derive the table name from the *original* filename, not the prefixed stored path.
    table_name = sanitize_table_name(Path(file.filename).name)
    try:
        table = source.ingest_file(dest, table_name=table_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to load file: {exc}") from exc

    if table not in session.tables:
        session.tables.append(table)

    return UploadResponse(
        session_id=session.id,
        tables=session.tables,
        schema_info=source.get_schema(),
    )


@router.post("/sessions/{session_id}/connect", response_model=UploadResponse)
def connect_database(session_id: str, req: ConnectRequest) -> UploadResponse:
    session = _require_session(session_id)
    try:
        source = session_manager.attach_sql(session, req.connection_url, req.label)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Connection failed: {exc}") from exc

    return UploadResponse(
        session_id=session.id,
        tables=session.tables,
        schema_info=source.get_schema(),
    )


@router.get("/sessions/{session_id}/schema")
def get_schema(session_id: str):
    session = _require_session(session_id)
    if session.datasource is None:
        raise HTTPException(status_code=400, detail="No data attached to this session yet.")
    return session.datasource.get_schema()


@router.post("/sessions/{session_id}/query", response_model=QueryResponse)
def run_query(session_id: str, req: QueryRequest) -> QueryResponse:
    """Direct read-only SQL execution (used for testing and the schema explorer)."""
    session = _require_session(session_id)
    if session.datasource is None:
        raise HTTPException(status_code=400, detail="No data attached to this session yet.")

    settings = get_settings()
    try:
        result = session.datasource.run_sql(
            req.query,
            max_rows=settings.max_query_rows,
            timeout_seconds=settings.query_timeout_seconds,
        )
    except UnsafeQueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=408, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Query error: {exc}") from exc

    return QueryResponse(result=result)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    _require_session(session_id)
    session_manager.delete(session_id)
    return {"deleted": session_id}
