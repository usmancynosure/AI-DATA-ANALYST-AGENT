"""FastAPI application entrypoint."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, datasources, health
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = get_settings()

app = FastAPI(
    title="AI Data Analyst Agent",
    version="0.1.0",
    description="Upload a CSV or connect a database, ask questions in plain English.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(datasources.router)
app.include_router(chat.router)


@app.get("/")
def root() -> dict:
    return {"name": app.title, "version": app.version, "docs": "/docs"}
