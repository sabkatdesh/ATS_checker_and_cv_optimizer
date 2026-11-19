"""Typed ATS result built from the deterministic checker."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.domain.ats.checker import compute_final_match
from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.jd.schemas import JobDescriptionStructured
from app.domain.match.schemas import round_half_up


class SectionScore(BaseModel, frozen=True):
    score: float
    matched: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class AtsMatch(BaseModel, frozen=True):
    applies: bool
    score: int | None = Field(default=None, ge=0, le=100)
    breakdown: dict[str, SectionScore] = Field(default_factory=dict)
    hard_gaps: list[str] = Field(default_factory=list)


def _section(raw: dict[str, Any]) -> SectionScore:
    return SectionScore(
        score=float(raw["score"]),
        matched=list(raw.get("matched", [])),
        missing=list(raw.get("missing", [])),
    )


def compute_ats(jd: JobDescriptionStructured, cv: UniversalCVStructured) -> AtsMatch:
    raw = compute_final_match(jd, cv)
    return AtsMatch(
        applies=True,
        score=round_half_up(raw["overall_score"]),
        breakdown={name: _section(s) for name, s in raw["section_scores"].items()},
        hard_gaps=list(raw["hard_gaps"]),
    )


def non_ats_match() -> AtsMatch:
    """Domains where keyword scanners are not used: no score, nothing to optimise for."""
    return AtsMatch(applies=False)
