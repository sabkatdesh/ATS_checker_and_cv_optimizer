"""Stage 2 nodes: detailed extraction and ATS match scoring."""

from __future__ import annotations

from typing import Any

import structlog

from app.domain.ats.checker import compute_final_match
from app.domain.cv.domain_config import Domain, should_run_ats
from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.jd.schemas import JobDescriptionStructured
from app.domain.parsing.safe_parser import safe_llm_parse
from app.pipeline.chains import Chains
from app.pipeline.nodes._helpers import _fallback_cv, _fallback_jd, _simplified_match
from app.pipeline.state import CombinedState

log = structlog.get_logger(__name__)


def detailed_extract_jd(state: CombinedState, *, chains: Chains) -> dict[str, Any]:
    log.info("pipeline.stage", stage="detailed_extract_jd")
    raw = chains.detailed_jd.invoke({"job_description": state["job_description"]})
    jd = safe_llm_parse(raw, JobDescriptionStructured, _fallback_jd())
    return {"structured_jd": jd}


def detailed_extract_cv(state: CombinedState, *, chains: Chains) -> dict[str, Any]:
    log.info("pipeline.stage", stage="detailed_extract_cv")
    domain = state.get("detected_domain", Domain.GENERAL.value)
    raw = chains.detailed_cv.invoke(
        {
            "user_resume": state["user_resume"],
            "domain": domain,
        }
    )
    cv = safe_llm_parse(raw, UniversalCVStructured, _fallback_cv())
    return {"structured_cv": cv}


def start_detailed_phase(state: CombinedState) -> dict[str, Any]:
    domain = state.get("detected_domain", "general")
    ats_applies = should_run_ats(domain)
    log.info("pipeline.stage", stage="start_detailed_phase", domain=domain, ats=ats_applies)
    return {}


def compute_match(state: CombinedState) -> dict[str, Any]:
    domain = state.get("detected_domain", Domain.GENERAL.value)
    counter = state.get("counter", 0)
    log.info("pipeline.stage", stage="compute_match", domain=domain, iteration=counter + 1)

    structured_cv = state.get("structured_cv")
    structured_jd = state.get("structured_jd")

    # Non-ATS domains: skip full scoring, return simplified result
    if not should_run_ats(domain):
        match_result = _simplified_match(structured_cv, structured_jd)
        log.info("pipeline.stage", stage="compute_match_skipped", domain=domain)
        return {"final_match": match_result}

    # ATS domains: run full scoring
    try:
        match_result = compute_final_match(structured_jd, structured_cv)
    except Exception as e:
        log.warning("pipeline.ats_failed", error_type=type(e).__name__)
        match_result = {
            "overall_score": 0,
            "section_scores": {},
            "hard_gaps": [],
            "rewrite_hints": {"title_alignment": "Unknown → Unknown", "missing_tools": []},
        }

    log.info("pipeline.stage", stage="ats_score", score=match_result["overall_score"])
    return {"final_match": match_result}


def check_ats_score(state: CombinedState) -> str:
    domain = state.get("detected_domain", Domain.GENERAL.value)
    counter = state.get("counter", 0)
    max_it = state.get("max_iterations", 2)

    # First pass: always rewrite at least once for every domain
    if counter == 0:
        log.info("pipeline.stage", stage="gate_rewrite", reason="first_pass", domain=domain)
        return "rewrite"

    # Non-ATS domains: one rewrite is enough
    if not should_run_ats(domain):
        log.info("pipeline.stage", stage="gate_end", reason="non_ats_done", domain=domain)
        return "end"

    # ATS domains: loop until score >= 90 or max iterations
    score = (state["final_match"] or {})["overall_score"]
    if score >= 90:
        log.info("pipeline.stage", stage="gate_end", reason="target_reached", score=score)
        return "end"
    if counter >= max_it:
        log.info("pipeline.stage", stage="gate_end", reason="max_iterations", score=score)
        return "end"

    log.info("pipeline.stage", stage="gate_rewrite", reason="below_target", score=score)
    return "rewrite"
