from fastapi import APIRouter, Depends

from app.api.deps import get_container
from app.container import Container

router = APIRouter()


@router.get("/templates")
def list_templates(c: Container = Depends(get_container)):
    """Return all available CV templates (public — no auth required)"""
    templates = c.store.get_cv_templates()
    return {"templates": templates}
