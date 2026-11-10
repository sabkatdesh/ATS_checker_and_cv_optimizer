"""Eligibility match models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.common import NullSafeListMixin
from app.domain.cv.domain_config import Domain


class Match(NullSafeListMixin, BaseModel):
    score: Literal[0, 30, 60, 100] | None = None
    verdict: (
        Literal[
            "Doesn't Align at all 0%",
            "Somewhat Align 30%",
            "Partially Align 60%",
            "Perfectly Align 100%",
        ]
        | None
    ) = None
    reason: list[str] = Field(default_factory=list)
    gaps_to_consider: list[str] = Field(default_factory=list)


class SummaryCV(NullSafeListMixin, BaseModel):
    """Lightweight CV summary used for fast eligibility check."""

    domain: Domain = Domain.GENERAL
    summary: str | None = None
    tools: list[str] = Field(default_factory=list)
    Job: str | None = None
    project: str | None = None
    hidden_tools: list[str] = Field(default_factory=list)
    experience: int | None = None
    education: list[str] = Field(default_factory=list)
    subject: list[str] = Field(default_factory=list)
