"""Eligibility models."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.domain.common import NullSafeListMixin
from app.domain.cv.domain_config import Domain


def round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


class Eligibility(NullSafeListMixin, BaseModel):
    """How well the candidate fits the job, 0-100; the threshold decision is made in code."""

    score: int = Field(ge=0, le=100)
    rationale: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)  # informational (D4)

    @field_validator("score", mode="before")
    @classmethod
    def _round_float(cls, value: Any) -> Any:
        if isinstance(value, float) and math.isfinite(value):
            return round_half_up(value)
        return value


class SummaryCV(NullSafeListMixin, BaseModel):
    """Lightweight CV summary used by the legacy quick-CV chain."""

    domain: Domain = Domain.GENERAL
    summary: str | None = None
    tools: list[str] = Field(default_factory=list)
    Job: str | None = None
    project: str | None = None
    hidden_tools: list[str] = Field(default_factory=list)
    experience: int | None = None
    education: list[str] = Field(default_factory=list)
    subject: list[str] = Field(default_factory=list)
