"""Read-only summary of a run's checkpoint for the status payload (extended by later tasks)."""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from app.pipeline.warnings import WarningCode


class JdMeta(BaseModel, frozen=True):
    job_title: str | None = None
    company_name: str | None = None
    domain: str | None = None


class SessionSummary(BaseModel, frozen=True):
    jd: JdMeta | None = None
    domain: str | None = None
    eligibility_score: int | None = None
    ats_before: int | None = None
    ats_after: int | None = None
    warnings: list[WarningCode] = Field(default_factory=list)


def ats_score_of(ats: Any) -> int | None:
    """Score of an ATS result: the legacy dict until Task 3, then AtsMatch.score."""
    if ats is None:
        return None
    raw = ats.get("overall_score") if isinstance(ats, Mapping) else getattr(ats, "score", None)
    return None if raw is None else round(raw)


def summarize(values: Mapping[str, Any]) -> SessionSummary | None:
    if not values:
        return None
    jd = values.get("jd")
    eligibility = values.get("eligibility")
    return SessionSummary(
        jd=None
        if jd is None
        else JdMeta(job_title=jd.job_title, company_name=jd.company_name, domain=jd.domain.value),
        domain=values.get("domain"),
        eligibility_score=None if eligibility is None else eligibility.score,
        ats_before=ats_score_of(values.get("ats_before")),
        ats_after=ats_score_of(values.get("ats")),
        warnings=[w.code for w in values.get("warnings", [])],
    )
