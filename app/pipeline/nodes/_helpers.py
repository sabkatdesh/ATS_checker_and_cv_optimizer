"""Fallback factories and small pure helpers shared by the nodes."""

from __future__ import annotations

from app.domain.cv.domain_config import Domain
from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.jd.schemas import JobDescriptionStructured, SummaryJD
from app.domain.match.schemas import Match, SummaryCV


def _fallback_summary_jd() -> SummaryJD:
    return SummaryJD()


def _fallback_summary_cv() -> SummaryCV:
    return SummaryCV(summary="", Job="Unknown", experience=0)


def _fallback_match() -> Match:
    return Match(
        score=0,
        verdict="Doesn't Align at all 0%",
        reason=["Could not determine match — please check your inputs."],
        gaps_to_consider=[],
    )


def _fallback_jd() -> JobDescriptionStructured:
    return JobDescriptionStructured()


def _fallback_cv() -> UniversalCVStructured:
    return UniversalCVStructured()


def _reconcile_domain(quick_cv: SummaryCV, quick_jd: SummaryJD) -> str:
    """
    Reconcile domain from both quick extractions.
    CV domain wins (the candidate knows their own profession).
    Falls back to JD domain, then GENERAL.
    """
    cv_domain = getattr(quick_cv, "domain", Domain.GENERAL)
    jd_domain = getattr(quick_jd, "domain", Domain.GENERAL)

    if cv_domain and cv_domain != Domain.GENERAL:
        return cv_domain.value if hasattr(cv_domain, "value") else str(cv_domain)
    if jd_domain and jd_domain != Domain.GENERAL:
        return jd_domain.value if hasattr(jd_domain, "value") else str(jd_domain)
    return Domain.GENERAL.value


def _normalize_budget(budget: dict) -> dict:
    return {
        "target_words": budget.get("target_words", 800),
        "max_roles": budget.get("max_roles", 4),
        "max_skills": budget.get("max_skills", 18),
        "max_projects": budget.get("max_projects", 0),
        "max_publications": budget.get("max_publications", 0),
        "max_certs": budget.get("max_certs", 3),
    }


def _simplified_match(cv, jd) -> dict:
    """Minimal match result for non-ATS domains. Score=100 means 'done'."""
    try:
        cv_role = cv.experience_summary.role_type or "Candidate"
    except AttributeError:
        cv_role = "Candidate"
    jd_title = getattr(jd, "job_title", None) or "Position"
    return {
        "overall_score": 100,
        "section_scores": {},
        "hard_gaps": [],
        "rewrite_hints": {
            "title_alignment": f"{cv_role} → {jd_title}",
            "missing_tools": [],
        },
    }


def _safe_json(obj) -> str:
    try:
        return obj.model_dump_json()
    except Exception:
        return str(obj)
