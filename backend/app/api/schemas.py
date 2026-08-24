"""Request/response models for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel

from app.datasources.base import QueryResult, SchemaInfo


class SessionResponse(BaseModel):
    session_id: str
    kind: str | None = None
    label: str | None = None
    tables: list[str] = []


class UploadResponse(BaseModel):
    session_id: str
    tables: list[str]
    schema_info: SchemaInfo


class ConnectRequest(BaseModel):
    connection_url: str
    label: str | None = None


class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    result: QueryResult
