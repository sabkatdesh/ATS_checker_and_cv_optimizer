"""Temporary."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def health_check():
    """Simple check to confirm API is running"""
    return {"status": "CV Optimizer API is running"}
