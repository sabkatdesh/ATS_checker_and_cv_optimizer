"""Eligibility match models."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from core.schemas.universal_cv import NullSafeListMixin
from core.schemas.domain_config import Domain


class Match(NullSafeListMixin, BaseModel):
    score: Optional[Literal[0, 30, 60, 100]] = None
    verdict: Optional[Literal[
        "Doesn't Align at all 0%",
        "Somewhat Align 30%",
        "Partially Align 60%",
        "Perfectly Align 100%",
    ]] = None
    reason: List[str] = Field(default_factory=list)
    gaps_to_consider: List[str] = Field(default_factory=list)


class SummaryCV(NullSafeListMixin, BaseModel):
    """Lightweight CV summary used for fast eligibility check."""
    domain: Domain = Domain.GENERAL
    summary: Optional[str] = None
    tools: List[str] = Field(default_factory=list)
    Job: Optional[str] = None
    project: Optional[str] = None
    hidden_tools: List[str] = Field(default_factory=list)
    experience: Optional[int] = None
    education: List[str] = Field(default_factory=list)
    subject: List[str] = Field(default_factory=list)
