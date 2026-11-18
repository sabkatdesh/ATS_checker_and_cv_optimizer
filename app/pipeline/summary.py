"""Read-only summary of a run's checkpoint for the status payload (extended by later tasks)."""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from app.domain.ats.schemas import AtsMatch
from app.domain.jd.meta import JdMeta, jd_meta
from app.domain.trust.report import TrustReport
from app.pipeline.errors import ErrorCode
from app.pipeline.hooks import Stage
from app.pipeline.warnings import WarningCode


class SessionSummary(BaseModel, frozen=True):
    jd: JdMeta | None = None
    domain: str | None = None
    eligibility_score: int | None = None
    ats_before: int | None = None
    ats_after: int | None = None
    trust_report: TrustReport | None = None
    warnings: list[WarningCode] = Field(default_factory=list)
    error_code: ErrorCode | None = None
    cancelled_stage: Stage | None = None


def ats_score_of(ats: AtsMatch | None) -> int | None:
    """Score of an ATS result; None when there is none or the domain is not ATS-scored."""
    return None if ats is None else ats.score


def summarize(
    values: Mapping[str, Any],
    error_code: ErrorCode | None = None,
    cancelled_stage: Stage | None = None,
) -> SessionSummary | None:
    if not values:
        if error_code is None and cancelled_stage is None:
            return None
        return SessionSummary(error_code=error_code, cancelled_stage=cancelled_stage)
    jd = values.get("jd")
    eligibility = values.get("eligibility")
    return SessionSummary(
        jd=None if jd is None else jd_meta(jd),
        domain=values.get("domain"),
        eligibility_score=None if eligibility is None else eligibility.score,
        ats_before=ats_score_of(values.get("ats_before")),
        ats_after=ats_score_of(values.get("ats")),
        trust_report=values.get("trust_report"),
        warnings=[w.code for w in values.get("warnings", [])],
        error_code=error_code,
        cancelled_stage=cancelled_stage,
    )
