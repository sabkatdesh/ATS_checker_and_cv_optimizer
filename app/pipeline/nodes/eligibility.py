"""Stage 1 nodes: quick extraction and the eligibility gate."""

from __future__ import annotations

from typing import Any

import structlog

from app.domain.cv.domain_config import Domain
from app.domain.jd.schemas import SummaryJD
from app.domain.match.schemas import Match, SummaryCV
from app.domain.parsing.safe_parser import safe_llm_parse
from app.pipeline.chains import Chains
from app.pipeline.nodes._helpers import (
    _fallback_match,
    _fallback_summary_cv,
    _fallback_summary_jd,
    _reconcile_domain,
)
from app.pipeline.state import CombinedState

log = structlog.get_logger(__name__)


def quick_extract_jd(state: CombinedState, *, chains: Chains) -> dict[str, Any]:
    log.info("pipeline.stage", stage="quick_extract_jd")
    raw = chains.quick_jd.invoke({"job_description": state["job_description"]})
    jd = safe_llm_parse(raw, SummaryJD, _fallback_summary_jd())
    return {"quick_jd": jd}


def quick_extract_cv(state: CombinedState, *, chains: Chains) -> dict[str, Any]:
    log.info("pipeline.stage", stage="quick_extract_cv")
    raw = chains.quick_cv.invoke({"user_resume": state["user_resume"]})
    cv = safe_llm_parse(raw, SummaryCV, _fallback_summary_cv())
    return {"quick_cv": cv}


def eligibility_check(state: CombinedState, *, chains: Chains) -> dict[str, Any]:
    log.info("pipeline.stage", stage="eligibility_check")

    jd_data = state.get("quick_jd")
    cv_data = state.get("quick_cv")

    if not jd_data or not cv_data:
        return {
            "detected_domain": Domain.GENERAL.value,
            "eligibility_verdict": _fallback_match(),
            "is_eligible": False,
            "eligibility_message": "[WARN] Could not read inputs. Please check your CV and JD.",
        }

    # Reconcile domain from both quick extractions
    detected_domain = _reconcile_domain(cv_data, jd_data)

    verdict_inputs = {
        "domain": detected_domain,
        "jd_job": getattr(jd_data, "Job", None) or "Not specified",
        "jd_experience": getattr(jd_data, "experience", None) or 0,
        "jd_tools": ", ".join(jd_data.tools) if jd_data.tools else "None",
        "jd_summary": getattr(jd_data, "summary", None) or "No summary",
        "cv_job": getattr(cv_data, "Job", None) or "Not specified",
        "cv_experience": getattr(cv_data, "experience", None) or 0,
        "cv_tools": ", ".join(cv_data.tools) if cv_data.tools else "None",
        "cv_summary": getattr(cv_data, "summary", None) or "No summary",
        "cv_education": ", ".join(cv_data.education) if cv_data.education else "None",
        "cv_project": getattr(cv_data, "project", None) or "No projects listed",
    }

    raw = chains.verdict.invoke(verdict_inputs)
    verdict = safe_llm_parse(raw, Match, _fallback_match())
    gaps = verdict.gaps_to_consider or []
    is_eligible = (verdict.score or 0) >= 30

    message = (
        f"[OK] Eligible! Score: {verdict.score}%. Domain: {detected_domain}. Proceeding..."
        if is_eligible
        else f"[NO] Not Eligible. Score: {verdict.score}%. {verdict.verdict}"
    )
    log.info(
        "pipeline.stage",
        stage="eligibility_result",
        eligible=is_eligible,
        score=verdict.score,
        domain=detected_domain,
    )

    return {
        "detected_domain": detected_domain,
        "eligibility_verdict": verdict,
        "is_eligible": is_eligible,
        "eligibility_message": message,
        "gaps_identified": gaps,
    }


def check_eligibility_gate(state: CombinedState) -> str:
    return "proceed_to_ats" if state["is_eligible"] else "stop"
