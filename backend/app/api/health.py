from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "model": settings.anthropic_model,
        "agent_enabled": bool(settings.anthropic_api_key),
    }
