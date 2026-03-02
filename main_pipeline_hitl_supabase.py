from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq
from dotenv import load_dotenv
import os

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from pydantic_class import (
    Match, SummaryCV, SummaryJD,
    JobDescriptionStructured, UserCVStructured, Re_write_UserCVStructured,
    SkillBlock, ExperienceBlock, EducationBlock,
    RequirementBlock, ResponsibilityBlock,
    UserMeta, UserSkillBlock, ExperienceSummary,
    CVQualityFlags,
)
from ats_checker import compute_final_match
from safe_parser import safe_llm_parse
from typing import TypedDict, Optional, List
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt
import json
import time

load_dotenv()
GROQ_API = os.environ.get("GROQ_API") or os.environ.get("GROQ_API_KEY")



# Model
llm = ChatGroq(
    model="openai/gpt-oss-120b",
    api_key=GROQ_API,
    temperature=0,
)

# ============================================================================
# PARSERS
# ============================================================================

parser_quick_jd = PydanticOutputParser(pydantic_object=SummaryJD)
parser_quick_cv = PydanticOutputParser(pydantic_object=SummaryCV)
verdict_parser = PydanticOutputParser(pydantic_object=Match)
parser_detailed_jd = PydanticOutputParser(pydantic_object=JobDescriptionStructured)
parser_detailed_cv = PydanticOutputParser(pydantic_object=UserCVStructured)

# ============================================================================
# TEMPLATES
# ============================================================================

template_quick_cv = PromptTemplate(
    template="Extract all information from this user cv - {user_resume} \n {format_instructions}",
    input_variables=["user_resume"],
    partial_variables={"format_instructions": parser_quick_cv.get_format_instructions()},
)

template_quick_jd = PromptTemplate(
    template="Extract all information from this Job Description - {job_description} \n {format_instructions}",
    input_variables=["job_description"],
    partial_variables={"format_instructions": parser_quick_jd.get_format_instructions()},
)

template_verdict = PromptTemplate(
    template="""Based on the following CV and Job Description, provide a matching score and verdict.

Job Description:
Job Title: {jd_job}
Required Experience: {jd_experience} years
Required Tools: {jd_tools}
Summary: {jd_summary}

Candidate Information:
Candidate Job: {cv_job}
Candidate Experience: {cv_experience} years
Candidate Tools: {cv_tools}
Candidate Summary: {cv_summary}
Education: {cv_education}
Projects: {cv_project}

Provide a score (0-100) and determine if the candidate is eligible for this position.
Focus on: domain alignment, experience level match, and core competencies.
Also list the top gaps that need to be addressed.

{format_instructions}""",
    input_variables=["jd_job", "jd_experience", "jd_tools", "jd_summary",
                     "cv_job", "cv_experience", "cv_tools", "cv_summary",
                     "cv_education", "cv_project"],
    partial_variables={"format_instructions": verdict_parser.get_format_instructions()},
)

template_detailed_jd = PromptTemplate(
    template="Extract all information from this Job Description - {job_description} \n {format_instructions}",
    input_variables=["job_description"],
    partial_variables={"format_instructions": parser_detailed_jd.get_format_instructions()},
)

template_detailed_cv = PromptTemplate(
    template="Extract all information from this user cv - {user_resume} \n {format_instructions}",
    input_variables=["user_resume"],
    partial_variables={"format_instructions": parser_detailed_cv.get_format_instructions()},
)

# ============================================================================
# CHAINS
# ============================================================================

quick_cv_raw_chain = template_quick_cv | llm | StrOutputParser()
quick_jd_raw_chain = template_quick_jd | llm | StrOutputParser()
verdict_raw_chain = template_verdict | llm | StrOutputParser()
detailed_jd_raw_chain = template_detailed_jd | llm | StrOutputParser()
detailed_cv_raw_chain = template_detailed_cv | llm | StrOutputParser()


# ============================================================================
# FALLBACKS
# ============================================================================

def make_jd_fallback() -> JobDescriptionStructured:
    return JobDescriptionStructured(
        responsibilities=ResponsibilityBlock(),
        requirements=RequirementBlock(),
        skills=SkillBlock(),
        experience=ExperienceBlock(),
        education=EducationBlock(),
    )


def make_cv_fallback() -> UserCVStructured:
    return UserCVStructured(
        meta=UserMeta(),
        skills=UserSkillBlock(),
        experience_summary=ExperienceSummary(),
        quality_flags=CVQualityFlags(),
    )


def make_summary_jd_fallback() -> SummaryJD:
    return SummaryJD()


def make_summary_cv_fallback() -> SummaryCV:
    return SummaryCV(
        summary="",
        Job="Unknown",
        project="",
        experience=0,
        education=[],
    )


def make_match_fallback() -> Match:
    return Match(
        score=0,
        verdict="Doesn't Align at all 0%",
        reason=["Could not determine match — please check your inputs."],
        gaps_to_consider=[]
    )


# ============================================================================
# STATE
# ============================================================================

class CombinedState(TypedDict):
    job_description: str
    user_resume: str

    quick_jd: Optional[SummaryJD]
    quick_cv: Optional[SummaryCV]
    eligibility_verdict: Optional[Match]
    is_eligible: bool
    eligibility_message: Optional[str]

    structured_jd: Optional[JobDescriptionStructured]
    structured_cv: Optional[UserCVStructured]
    final_match: Optional[dict]

    # HITL - Simple Q&A storage
    gaps_identified: List[str]
    user_qna: Optional[str]

    # Session info
    hitl_session_id: str
    hitl_awaiting_input: bool
    re_write_cv: Optional[str]
    counter: int
    max_iterations: int


# ============================================================================
# PHASE 1 NODES
# ============================================================================

def quick_extract_jd(state: CombinedState) -> dict:
    print("\n[Phase 1] Quick extracting JD...")
    raw = quick_jd_raw_chain.invoke({"job_description": state["job_description"]})
    jd = safe_llm_parse(raw, SummaryJD, make_summary_jd_fallback())
    return {"quick_jd": jd}


def quick_extract_cv(state: CombinedState) -> dict:
    print("[Phase 1] Quick extracting CV...")
    raw = quick_cv_raw_chain.invoke({"user_resume": state["user_resume"]})
    cv = safe_llm_parse(raw, SummaryCV, make_summary_cv_fallback())
    return {"quick_cv": cv}


def eligibility_check(state: CombinedState) -> dict:
    print("[Phase 1] Checking eligibility...")

    jd_data = state.get("quick_jd")
    cv_data = state.get("quick_cv")

    if not jd_data or not cv_data:
        return {
            "eligibility_verdict": make_match_fallback(),
            "is_eligible": False,
            "eligibility_message": "⚠️ Could not read inputs. Please check your CV and JD."
        }

    verdict_inputs = {
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

    raw = verdict_raw_chain.invoke(verdict_inputs)
    verdict = safe_llm_parse(raw, Match, make_match_fallback())
    gaps = verdict.gaps_to_consider or []

    is_eligible = verdict.score >= 30

    message = (
        f"✓ Eligible! Score: {verdict.score}%. Proceeding to ATS optimization..."
        if is_eligible else
        f"✗ Not Eligible. Score: {verdict.score}%. {verdict.verdict}"
    )
    print(f"[Phase 1] {message}")

    return {
        "eligibility_verdict": verdict,
        "is_eligible": is_eligible,
        "eligibility_message": message,
        "gaps_identified": gaps,
    }


def check_eligibility_gate(state: CombinedState) -> str:
    return "proceed_to_ats" if state["is_eligible"] else "stop"


def hitl_node(state: CombinedState) -> dict:
    """
    HITL Node - Only pauses if we have gaps AND no user feedback yet
    """
    gaps = state.get("gaps_identified", [])
    user_qna = state.get("user_qna")

    # If we already have user feedback, proceed without interrupting
    if user_qna:
        print("[HITL] User feedback already provided, proceeding...")
        return {
            "hitl_awaiting_input": False,
            "user_qna": user_qna
        }

    # If no gaps, proceed normally
    if not gaps:
        return {
            "hitl_awaiting_input": False,
            "user_qna": "No gaps identified"
        }

    # Show gaps and pause
    print("\n" + "=" * 70)
    print("⏸️  GRAPH PAUSED - AWAITING USER FEEDBACK")
    print("=" * 70)
    print(f"\nGaps Identified: {len(gaps)}\n")

    for i, gap in enumerate(gaps, 1):
        print(f"{i}. {gap}\n")

    print("[Graph is now paused. Please answer the questions...]")
    print("=" * 70 + "\n")

    # Pause graph execution
    interrupt({
        "type": "gap_confirmation",
        "gaps": gaps,
        "message": "Please provide user feedback"
    })

    # When resumed, return with user_qna from state
    return {
        "hitl_awaiting_input": False,
        "user_qna": state.get("user_qna", "")
    }


# ============================================================================
# PHASE 2 NODES
# ============================================================================

def detailed_extract_jd(state: CombinedState) -> dict:
    print("\n[Phase 2] Detailed extracting JD...")
    raw = detailed_jd_raw_chain.invoke({"job_description": state["job_description"]})
    jd = safe_llm_parse(raw, JobDescriptionStructured, make_jd_fallback())
    return {"structured_jd": jd}


def detailed_extract_cv(state: CombinedState) -> dict:
    print("[Phase 2] Detailed extracting CV...")
    raw = detailed_cv_raw_chain.invoke({"user_resume": state["user_resume"]})
    cv = safe_llm_parse(raw, UserCVStructured, make_cv_fallback())
    return {"structured_cv": cv}


def start_detailed_phase(state: CombinedState) -> dict:
    print("\n[Phase 2] Starting detailed ATS optimization...")
    return {}


def compute_match(state: CombinedState) -> dict:
    print(f"[Phase 2] Computing ATS match (Iteration {state.get('counter', 0) + 1})...")
    try:
        match_result = compute_final_match(state["structured_jd"], state["structured_cv"])
    except Exception as e:
        print(f"⚠️ ATS match computation failed: {e}. Using zero score.")
        match_result = {
            "overall_score": 0,
            "section_scores": {},
            "hard_gaps": [],
            "rewrite_hints": {"title_alignment": "Unknown → Unknown", "missing_tools": []}
        }
    print(f"[Phase 2] ATS Score: {match_result['overall_score']}%")
    return {"final_match": match_result}


def rewrite_cv_node(state: CombinedState) -> dict:
    print(f"[Phase 2] Rewriting CV (Attempt {state.get('counter', 0) + 1})...")

    if state.get("counter", 0) >= 10:
        print("⚠️ Safety ceiling reached. Stopping rewrite loop.")
        return {"structured_cv": state["structured_cv"], "counter": 10}

    total_years = (
                      state["structured_cv"].experience_summary.total_years
                      if state.get("structured_cv") and state["structured_cv"].experience_summary
                      else 0
                  ) or 0

    if total_years <= 1:
        tier = "fresher"
    elif total_years <= 3:
        tier = "junior_mid"
    elif total_years <= 5:
        tier = "mid_senior"
    else:
        tier = "senior"

    BUDGET_RULES = {
        "fresher": {"target_words": 650, "max_roles": 2, "max_skills": 12, "max_projects": 2, "max_certs": 1},
        "junior_mid": {"target_words": 850, "max_roles": 3, "max_skills": 18, "max_projects": 2, "max_certs": 2},
        "mid_senior": {"target_words": 1000, "max_roles": 5, "max_skills": 22, "max_projects": 2, "max_certs": 3},
        "senior": {"target_words": 1100, "max_roles": 6, "max_skills": 25, "max_projects": 2, "max_certs": 3},
    }
    budget = BUDGET_RULES[tier]

    section_scores = state["final_match"].get("section_scores", {})
    must_have_missing = section_scores.get("must_have", {}).get("missing", [])
    skills_missing = section_scores.get("skills", {}).get("missing", [])
    tools_missing = section_scores.get("tools", {}).get("missing", [])

    parser_rewrite_cv = PydanticOutputParser(pydantic_object=Re_write_UserCVStructured)

    cv_writing_prompt = PromptTemplate(
        template="""
You are a senior executive CV strategist and ATS optimization expert.

Rewrite the CV to maximize ATS alignment while respecting strict structural limits.

=========================
DYNAMIC SIZE LIMITS
=========================

• Target total word count: {target_words}
• Include ALL work experience roles from the CV, up to a maximum of {max_roles} roles. Do NOT drop real roles.
• Maximum hard_skills: {max_skills}
• Maximum projects: {max_projects}
• Maximum certifications: {max_certs}

=========================
CRITICAL ATS FIXES REQUIRED
=========================

You MUST explicitly incorporate the following missing items where truthful and appropriate:

Must-Have Missing:
{must_have_missing}

Skills Missing:
{skills_missing}

Tools Missing:
{tools_missing}

=========================
USER FEEDBACK ON GAPS
=========================

{user_feedback}

=========================
RULES
=========================

1. Use exact JD terminology where possible.
2. Do NOT invent companies, degrees, or fake experience.
3. Consider user feedback - only add skills if user confirmed them.
4. Improve measurable impact.
5. Prioritize JD-relevant keywords.
6. Avoid repetition and keyword stuffing.
7. Keep tone natural and executive-level.
8. Ensure skills/tools fields contain explicit tokens for ATS detection.

=========================

CURRENT CV:
{cv_text}

JOB DESCRIPTION:
{jd_text}

CURRENT ATS SCORE: {ats_score}

Title Alignment Suggestion:
{title_alignment}

=========================

Return ONLY valid structured output matching the Pydantic schema.

{format_instructions}
""",
        input_variables=[
            "cv_text", "jd_text", "ats_score",
            "must_have_missing", "skills_missing", "tools_missing",
            "title_alignment", "target_words", "max_roles",
            "max_skills", "max_projects", "max_certs",
            "user_feedback"
        ],
        partial_variables={"format_instructions": parser_rewrite_cv.get_format_instructions()},
    )

    cv_rewrite_raw_chain = cv_writing_prompt | llm | StrOutputParser()

    raw = cv_rewrite_raw_chain.invoke({
        "cv_text": (
            state["structured_cv"].model_dump_json()
            if state.get("structured_cv") else state["user_resume"]
        ),
        "jd_text": (
            state["structured_jd"].model_dump_json()
            if state.get("structured_jd") else state["job_description"]
        ),
        "ats_score": state["final_match"]["overall_score"],
        "must_have_missing": must_have_missing,
        "skills_missing": skills_missing,
        "tools_missing": tools_missing,
        "title_alignment": state["final_match"]["rewrite_hints"].get("title_alignment", "N/A"),
        "target_words": budget["target_words"],
        "max_roles": budget["max_roles"],
        "max_skills": budget["max_skills"],
        "max_projects": budget["max_projects"],
        "max_certs": budget["max_certs"],
        "user_feedback": state.get("user_qna", "No user feedback provided"),
    })

    rewritten_cv = safe_llm_parse(
        raw,
        Re_write_UserCVStructured,
        fallback=state["structured_cv"]
    )

    return {
        "structured_cv": rewritten_cv,
        "counter": state.get("counter", 0) + 1,
    }


def check_ats_score(state: CombinedState) -> str:
    score = state["final_match"]["overall_score"]
    counter = state.get("counter", 0)
    max_it = state.get("max_iterations", 2)

    if score >= 90:
        print(f"[Phase 2] ✓ Target achieved! Score: {score}%")
        return "end"
    if counter >= max_it:
        print(f"[Phase 2] Max iterations reached. Final score: {score}%")
        return "end"

    print(f"[Phase 2] Score {score}% < 90%. Rewriting CV...")
    return "rewrite"


# ============================================================================
# GRAPH with CHECKPOINTER
# ============================================================================


workflow = StateGraph(CombinedState)

workflow.add_node("quick_extract_jd", quick_extract_jd)
workflow.add_node("quick_extract_cv", quick_extract_cv)
workflow.add_node("eligibility_check", eligibility_check)
workflow.add_node("hitl_node", hitl_node)
workflow.add_node("start_detailed_phase", start_detailed_phase)
workflow.add_node("detailed_extract_jd", detailed_extract_jd)
workflow.add_node("detailed_extract_cv", detailed_extract_cv)
workflow.add_node("compute_match", compute_match)
workflow.add_node("rewrite_cv", rewrite_cv_node)

workflow.add_edge(START, "quick_extract_jd")
workflow.add_edge(START, "quick_extract_cv")
workflow.add_edge("quick_extract_jd", "eligibility_check")
workflow.add_edge("quick_extract_cv", "eligibility_check")

workflow.add_conditional_edges(
    "eligibility_check",
    check_eligibility_gate,
    {"stop": END, "proceed_to_ats": "hitl_node"},
)
workflow.add_edge("hitl_node", "start_detailed_phase")
workflow.add_edge("start_detailed_phase", "detailed_extract_jd")
workflow.add_edge("start_detailed_phase", "detailed_extract_cv")
workflow.add_edge("detailed_extract_jd", "compute_match")
workflow.add_edge("detailed_extract_cv", "compute_match")

workflow.add_conditional_edges(
    "compute_match",
    check_ats_score,
    {"rewrite": "rewrite_cv", "end": END}
)

workflow.add_edge("rewrite_cv", "compute_match")

app = workflow.compile(checkpointer=MemorySaver())

# ============================================================================
# API FUNCTIONS — called by FastAPI, not the terminal
# ============================================================================

def run_pipeline_for_user(
    job_description: str,
    user_resume_text: str,
    thread_id: str,
    max_iterations: int = 2
) -> dict:
    """
    Called by api.py
    Runs the full pipeline and returns final state
    """
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "job_description": job_description,
        "user_resume": user_resume_text,
        "quick_jd": None,
        "quick_cv": None,
        "eligibility_verdict": None,
        "is_eligible": False,
        "eligibility_message": None,
        "structured_jd": None,
        "structured_cv": None,
        "final_match": None,
        "re_write_cv": None,
        "counter": 0,
        "max_iterations": max_iterations,
        "gaps_identified": [],
        "user_qna": None,
        "hitl_session_id": thread_id,
        "hitl_awaiting_input": False,
    }

    result = app.invoke(initial_state, config)
    return result


def get_pipeline_state(thread_id: str) -> dict:
    """
    Check current state of a pipeline run
    Returns state values and what node is next
    """
    config = {"configurable": {"thread_id": thread_id}}
    state = app.get_state(config)

    if not state:
        return {"status": "not_found"}

    is_paused_at_hitl = (
        state.next and
        "hitl_node" in state.next
    )

    return {
        "values": state.values,
        "is_paused_at_hitl": is_paused_at_hitl,
        "next": list(state.next) if state.next else []
    }


def resume_pipeline_for_user(thread_id: str, user_qna: str) -> dict:
    """
    Called by api.py after user answers HITL questions
    Resumes from where pipeline paused
    """
    config = {"configurable": {"thread_id": thread_id}}

    # Inject user answers into the paused state
    app.update_state(config, {"user_qna": user_qna})

    # Resume — drive execution to completion
    for event in app.stream(None, config):
        pass

    # Return final state
    final_state = app.get_state(config)
    return final_state.values

