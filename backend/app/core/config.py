"""Application settings, loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Claude API (used from Phase 3 onward)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"

    # Server
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    # Storage
    data_dir: Path = Path(".data")

    # SQL safety
    max_query_rows: int = 10_000
    query_timeout_seconds: int = 30

    # Sandbox (Phase 2)
    sandbox_image: str = "ai-analyst-sandbox:latest"
    sandbox_timeout_seconds: int = 30
    sandbox_memory_limit: str = "512m"
    sandbox_cpu_limit: float = 1.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    def ensure_dirs(self) -> None:
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
