"""CV rewrite node."""

from __future__ import annotations

from typing import Any

import structlog

from app.domain.cv.domain_config import Domain, get_budget
from app.domain.cv.rewrite import RewrittenCV
from app.domain.parsing.safe_parser import safe_llm_parse
from app.pipeline.chains import Chains
from app.pipeline.nodes._helpers import _normalize_budget, _safe_json
from app.pipeline.prompts import get_domain_guidance
from app.pipeline.state import CombinedState

log = structlog.get_logger(__name__)


def rewrite_cv_node(state: CombinedState, *, chains: Chains) -> dict[str, Any]:
    counter = state.get("counter", 0)
    domain = state.get("detected_domain", Domain.GENERAL.value)
    log.info("pipeline.stage", stage="rewrite_cv", domain=domain, attempt=counter + 1)

    if counter >= 10:
        log.warning("pipeline.safety_ceiling", counter=counter)
        return {"structured_cv": state["structured_cv"], "counter": 10}

    # Determine seniority tier from experience summary
    structured_cv = state.get("structured_cv")
    total_years = 0
    try:
        if structured_cv and structured_cv.experience_summary:
            total_years = structured_cv.experience_summary.total_years or 0
    except AttributeError:
        pass

    # Domain-aware budget
    raw_budget = get_budget(domain, total_years)
    budget = _normalize_budget(raw_budget)

    # ATS-specific gap hints (empty for non-ATS domains)
    final_match = state.get("final_match") or {}
    section_scores = final_match.get("section_scores", {})
    must_have_missing = section_scores.get("must_have", {}).get("missing", [])
    skills_missing = section_scores.get("skills", {}).get("missing", [])
    tools_missing = section_scores.get("tools", {}).get("missing", [])

    raw = chains.rewrite.invoke(
        {
            "domain": domain,
            "domain_guidance": get_domain_guidance(domain),
            "target_words": budget["target_words"],
            "max_roles": budget["max_roles"],
            "max_skills": budget["max_skills"],
            "max_projects": budget["max_projects"],
            "max_publications": budget["max_publications"],
            "max_certs": budget["max_certs"],
            "must_have_missing": must_have_missing or "None",
            "skills_missing": skills_missing or "None",
            "tools_missing": tools_missing or "None",
            "user_feedback": state.get("user_qna") or "No user feedback provided",
            "cv_text": _safe_json(structured_cv) if structured_cv else state.get("user_resume", ""),
            "jd_text": _safe_json(state.get("structured_jd"))
            if state.get("structured_jd")
            else state.get("job_description", ""),
            "ats_score": final_match.get("overall_score", "N/A"),
            "title_alignment": final_match.get("rewrite_hints", {}).get("title_alignment", "N/A"),
        }
    )

    rewritten_cv = safe_llm_parse(raw, RewrittenCV, structured_cv)  # type: ignore[type-var]

    return {
        "structured_cv": rewritten_cv,
        "counter": counter + 1,
    }
