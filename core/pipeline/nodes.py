"""
Pipeline node functions — Phase 4 domain-aware implementation.

Key Phase 4 changes vs the original flat pipeline:
  1. Quick extraction uses new core/schemas types with domain fields
  2. eligibility_check propagates detected_domain into state
  3. compute_match is conditional — skips full ATS for non-ATS domains
  4. check_ats_score always runs one rewrite pass; non-ATS exits after one pass
  5. rewrite_cv_node uses DOMAIN_BUDGET_RULES[domain] for budget limits
  6. Rewrite prompt has hard evidence-only constraint at the top
"""
from __future__ import annotations

import json

from langchain_core.output_parsers import StrOutputParser
from langgraph.types import interrupt

from core.llm_client import get_llm
from core.schemas.match_schemas import SummaryCV, Match
from core.schemas.jd_schemas import SummaryJD, JobDescriptionStructured
from core.schemas.universal_cv import UniversalCVStructured
from core.schemas.rewrite_schemas import RewrittenCV
from core.schemas.domain_config import Domain, get_budget, should_run_ats
from core.pipeline.state import CombinedState
from core.pipeline.prompts import (
    QUICK_CV_PROMPT, QUICK_JD_PROMPT, VERDICT_PROMPT,
    DETAILED_JD_PROMPT, DETAILED_CV_PROMPT, REWRITE_PROMPT,
    COVER_LETTER_PROMPT, parser_rewrite, parser_cover_letter, get_domain_guidance,
)
from core.schemas.cover_letter_schemas import CoverLetterStructured
from core.ats.ats_checker import compute_final_match
from core.parsers.safe_parser import safe_llm_parse

llm = get_llm()


# ── Raw chains ───────────────────────────────────────────────────────────────────

_quick_cv_chain = QUICK_CV_PROMPT | llm | StrOutputParser()
_quick_jd_chain = QUICK_JD_PROMPT | llm | StrOutputParser()
_verdict_chain = VERDICT_PROMPT | llm | StrOutputParser()
_detailed_jd_chain = DETAILED_JD_PROMPT | llm | StrOutputParser()
_detailed_cv_chain = DETAILED_CV_PROMPT | llm | StrOutputParser()
_rewrite_chain = REWRITE_PROMPT | llm | StrOutputParser()
_cover_letter_chain = COVER_LETTER_PROMPT | llm | StrOutputParser()


# ── Fallback factories ────────────────────────────────────────────────────────────

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


# ── Helpers ───────────────────────────────────────────────────────────────────────

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


# ── Phase 1 nodes ────────────────────────────────────────────────────────────────

def quick_extract_jd(state: CombinedState) -> dict:
    print("\n[Stage 1] Quick extracting JD + domain...")
    raw = _quick_jd_chain.invoke({"job_description": state["job_description"]})
    jd = safe_llm_parse(raw, SummaryJD, _fallback_summary_jd())
    return {"quick_jd": jd}


def quick_extract_cv(state: CombinedState) -> dict:
    print("[Stage 1] Quick extracting CV + domain...")
    raw = _quick_cv_chain.invoke({"user_resume": state["user_resume"]})
    cv = safe_llm_parse(raw, SummaryCV, _fallback_summary_cv())
    return {"quick_cv": cv}


def eligibility_check(state: CombinedState) -> dict:
    print("[Stage 1] Checking eligibility...")

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

    raw = _verdict_chain.invoke(verdict_inputs)
    verdict = safe_llm_parse(raw, Match, _fallback_match())
    gaps = verdict.gaps_to_consider or []
    is_eligible = (verdict.score or 0) >= 30

    message = (
        f"[OK] Eligible! Score: {verdict.score}%. Domain: {detected_domain}. Proceeding..."
        if is_eligible else
        f"[NO] Not Eligible. Score: {verdict.score}%. {verdict.verdict}"
    )
    print(f"[Stage 1] {message}")

    return {
        "detected_domain": detected_domain,
        "eligibility_verdict": verdict,
        "is_eligible": is_eligible,
        "eligibility_message": message,
        "gaps_identified": gaps,
    }


def check_eligibility_gate(state: CombinedState) -> str:
    return "proceed_to_ats" if state["is_eligible"] else "stop"


def hitl_node(state: CombinedState) -> dict:
    """HITL node — pauses when gaps exist and no user feedback yet. Unchanged from Phase 3."""
    gaps = state.get("gaps_identified", [])
    user_qna = state.get("user_qna")

    if user_qna:
        print("[HITL] User feedback already provided, proceeding...")
        return {"hitl_awaiting_input": False, "user_qna": user_qna}

    if not gaps:
        return {"hitl_awaiting_input": False, "user_qna": "No gaps identified"}

    print("\n" + "=" * 70)
    print("[PAUSED] GRAPH PAUSED — AWAITING USER FEEDBACK")
    print("=" * 70)
    print(f"\nGaps Identified: {len(gaps)}\n")
    for i, gap in enumerate(gaps, 1):
        print(f"{i}. {gap}\n")

    interrupt({
        "type": "gap_confirmation",
        "gaps": gaps,
        "message": "Please provide user feedback on the listed gaps",
    })

    return {
        "hitl_awaiting_input": False,
        "user_qna": state.get("user_qna", ""),
    }


# ── Phase 2 nodes ────────────────────────────────────────────────────────────────

def detailed_extract_jd(state: CombinedState) -> dict:
    print("\n[Stage 2] Detailed extracting JD...")
    raw = _detailed_jd_chain.invoke({"job_description": state["job_description"]})
    jd = safe_llm_parse(raw, JobDescriptionStructured, _fallback_jd())
    return {"structured_jd": jd}


def detailed_extract_cv(state: CombinedState) -> dict:
    print("[Stage 2] Detailed extracting CV...")
    domain = state.get("detected_domain", Domain.GENERAL.value)
    raw = _detailed_cv_chain.invoke({
        "user_resume": state["user_resume"],
        "domain": domain,
    })
    cv = safe_llm_parse(raw, UniversalCVStructured, _fallback_cv())
    return {"structured_cv": cv}


def start_detailed_phase(state: CombinedState) -> dict:
    domain = state.get("detected_domain", "general")
    ats_applies = should_run_ats(domain)
    print(f"\n[Stage 2] Starting — domain={domain}, ATS scoring={'ON' if ats_applies else 'OFF'}")
    return {}


def compute_match(state: CombinedState) -> dict:
    domain = state.get("detected_domain", Domain.GENERAL.value)
    counter = state.get("counter", 0)
    print(f"[Stage 2] Computing match (domain={domain}, iteration={counter + 1})...")

    structured_cv = state.get("structured_cv")
    structured_jd = state.get("structured_jd")

    # Non-ATS domains: skip full scoring, return simplified result
    if not should_run_ats(domain):
        match_result = _simplified_match(structured_cv, structured_jd)
        print(f"[Stage 2] Non-ATS domain — skipping full ATS scoring.")
        return {"final_match": match_result}

    # ATS domains: run full scoring
    try:
        match_result = compute_final_match(structured_jd, structured_cv)
    except Exception as e:
        print(f"[WARN] ATS match computation failed: {e}. Using zero score.")
        match_result = {
            "overall_score": 0,
            "section_scores": {},
            "hard_gaps": [],
            "rewrite_hints": {"title_alignment": "Unknown → Unknown", "missing_tools": []},
        }

    print(f"[Stage 2] ATS Score: {match_result['overall_score']}%")
    return {"final_match": match_result}


def check_ats_score(state: CombinedState) -> str:
    domain = state.get("detected_domain", Domain.GENERAL.value)
    counter = state.get("counter", 0)
    max_it = state.get("max_iterations", 2)

    # First pass — always rewrite at least once for every domain
    if counter == 0:
        print(f"[Stage 2] First pass — scheduling rewrite (domain={domain})")
        return "rewrite"

    # Non-ATS domains: one rewrite is enough
    if not should_run_ats(domain):
        print(f"[Stage 2] Non-ATS domain — one rewrite pass complete, ending.")
        return "end"

    # ATS domains: loop until score >= 90 or max iterations
    score = state["final_match"]["overall_score"]
    if score >= 90:
        print(f"[Stage 2] Target score achieved ({score}%). Ending.")
        return "end"
    if counter >= max_it:
        print(f"[Stage 2] Max iterations ({max_it}) reached. Final score: {score}%. Ending.")
        return "end"

    print(f"[Stage 2] Score {score}% < 90%. Rewriting CV (attempt {counter + 1})...")
    return "rewrite"


def rewrite_cv_node(state: CombinedState) -> dict:
    counter = state.get("counter", 0)
    domain = state.get("detected_domain", Domain.GENERAL.value)
    print(f"[Stage 2] Rewriting CV (domain={domain}, attempt {counter + 1})...")

    if counter >= 10:
        print("[WARN] Safety ceiling reached. Stopping rewrite loop.")
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

    raw = _rewrite_chain.invoke({
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
        "jd_text": _safe_json(state.get("structured_jd")) if state.get("structured_jd") else state.get("job_description", ""),
        "ats_score": final_match.get("overall_score", "N/A"),
        "title_alignment": final_match.get("rewrite_hints", {}).get("title_alignment", "N/A"),
    })

    rewritten_cv = safe_llm_parse(raw, RewrittenCV, structured_cv)

    return {
        "structured_cv": rewritten_cv,
        "counter": counter + 1,
    }


# ── Cover Letter nodes (Phase 6) ─────────────────────────────────────────────────

def cover_letter_hitl_node(state: CombinedState) -> dict:
    """
    Second HITL interrupt — pauses so the user can confirm tone + length.
    - If cover_letter_requested=False → sets hitl_done=False, graph routes to END.
    - If tone+length already set → sets hitl_done=True, graph routes to generate.
    - Otherwise → interrupts pipeline, waiting for POST /cover-letter-options.
    """
    if not state.get("cover_letter_requested"):
        return {"cover_letter_hitl_done": False}

    tone = state.get("cover_letter_tone")
    length = state.get("cover_letter_length")

    if tone and length:
        print(f"[Cover Letter HITL] Options ready (tone={tone}, length={length}). Proceeding.")
        return {"cover_letter_hitl_done": True}

    print("\n" + "=" * 70)
    print("[PAUSED] COVER LETTER OPTIONS — AWAITING USER INPUT")
    print("=" * 70)

    interrupt({
        "type": "cover_letter_options",
        "message": (
            "Choose cover letter options:\n"
            "  tone:   'formal' or 'conversational'\n"
            "  length: 'short' (~150 words) or 'standard' (~300 words)"
        ),
    })

    return {"cover_letter_hitl_done": True}


def check_cover_letter_gate(state: CombinedState) -> str:
    """Conditional edge after cover_letter_hitl — route to generate or END."""
    return "generate" if state.get("cover_letter_hitl_done") else "done"


def _fallback_cover_letter() -> CoverLetterStructured:
    return CoverLetterStructured(
        salutation="Dear Hiring Manager,",
        opening_paragraph="I am excited to apply for this position.",
        body_paragraphs=[],
        closing_paragraph="Thank you for your consideration.",
        sign_off="Sincerely,",
    )


def generate_cover_letter_node(state: CombinedState) -> dict:
    """Generate the cover letter using the LLM."""
    tone = state.get("cover_letter_tone") or "formal"
    length = state.get("cover_letter_length") or "standard"
    word_target = 150 if length == "short" else 300

    structured_cv = state.get("structured_cv")
    structured_jd = state.get("structured_jd")
    gaps = state.get("gaps_identified", [])

    print(f"[Cover Letter] Generating (tone={tone}, length={length}, ~{word_target} words)...")

    raw = _cover_letter_chain.invoke({
        "tone": tone,
        "length": length,
        "word_target": word_target,
        "cv_text": _safe_json(structured_cv) if structured_cv else state.get("user_resume", ""),
        "jd_text": _safe_json(structured_jd) if structured_jd else state.get("job_description", ""),
        "gaps": "\n".join(f"- {g}" for g in gaps) if gaps else "None",
    })

    result = safe_llm_parse(raw, CoverLetterStructured, _fallback_cover_letter())
    print("[Cover Letter] Generation complete.")

    return {"cover_letter_result": result}
