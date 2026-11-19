from fastapi import APIRouter, Depends

from app.adapters.db.pool import db_health
from app.api.deps import get_container
from app.api.errors import AppError
from app.config.settings import ConfigError
from app.container import Container

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/deep")
def health_deep(c: Container = Depends(get_container)) -> dict[str, str]:
    try:
        ok = db_health(c.pool)
    except ConfigError:
        ok = False
    if not ok:
        raise AppError("DB_DOWN", 503, "Database unavailable", "The database is not reachable.")
    return {"db": "ok"}


@router.get("/")
def health_check():
    """Simple check to confirm API is running"""
    return {"status": "CV Optimizer API is running"}
