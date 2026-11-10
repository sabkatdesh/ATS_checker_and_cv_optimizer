"""
Pipeline graph — wires all nodes into the LangGraph StateGraph.

Public API (called by api.py via main_pipeline_hitl_supabase.py):
  run_pipeline_for_user(job_description, user_resume_text, thread_id, max_iterations)
  get_pipeline_state(thread_id) → dict
  resume_pipeline_for_user(thread_id, user_qna) → dict
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from core.pipeline.state import CombinedState
from core.pipeline.nodes import (
    quick_extract_jd, quick_extract_cv, eligibility_check,
    check_eligibility_gate, hitl_node, start_detailed_phase,
    detailed_extract_jd, detailed_extract_cv,
    compute_match, check_ats_score, rewrite_cv_node,
    check_cover_letter_gate, cover_letter_hitl_node, generate_cover_letter_node,
)

# ── Graph wiring ──────────────────────────────────────────────────────────────────

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
workflow.add_node("cover_letter_hitl", cover_letter_hitl_node)
workflow.add_node("generate_cover_letter", generate_cover_letter_node)

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
    {"rewrite": "rewrite_cv", "end": "cover_letter_hitl"},
)

workflow.add_edge("rewrite_cv", "compute_match")

workflow.add_conditional_edges(
    "cover_letter_hitl",
    check_cover_letter_gate,
    {"generate": "generate_cover_letter", "done": END},
)

workflow.add_edge("generate_cover_letter", END)

_app = workflow.compile(checkpointer=MemorySaver(serde=JsonPlusSerializer()))


# ── Public API ────────────────────────────────────────────────────────────────────

def run_pipeline_for_user(
    job_description: str,
    user_resume_text: str,
    thread_id: str,
    max_iterations: int = 2,
    cover_letter_requested: bool = False,
    cover_letter_tone: str | None = None,
    cover_letter_length: str | None = None,
) -> dict:
    """Start a fresh pipeline run. Returns final state dict."""
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: CombinedState = {
        "job_description": job_description,
        "user_resume": user_resume_text,
        "detected_domain": "general",
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
        "cover_letter_requested": cover_letter_requested,
        "cover_letter_tone": cover_letter_tone,
        "cover_letter_length": cover_letter_length,
        "cover_letter_result": None,
        "cover_letter_hitl_done": False,
    }

    return _app.invoke(initial_state, config)


def get_pipeline_state(thread_id: str) -> dict:
    """Return current pipeline state; checks for HITL pause."""
    config = {"configurable": {"thread_id": thread_id}}
    state = _app.get_state(config)

    if not state:
        return {"status": "not_found"}

    is_paused_at_hitl = bool(state.next and "hitl_node" in state.next)

    return {
        "values": state.values,
        "is_paused_at_hitl": is_paused_at_hitl,
        "next": list(state.next) if state.next else [],
    }


def resume_pipeline_for_user(thread_id: str, user_qna: str) -> dict:
    """Inject HITL answers and resume execution to completion."""
    config = {"configurable": {"thread_id": thread_id}}
    _app.update_state(config, {"user_qna": user_qna})

    for _ in _app.stream(None, config):
        pass

    final_state = _app.get_state(config)
    return final_state.values


def resume_cover_letter_for_user(thread_id: str, tone: str, length: str) -> dict:
    """Inject cover letter options (tone+length) and resume execution."""
    config = {"configurable": {"thread_id": thread_id}}
    _app.update_state(config, {
        "cover_letter_tone": tone,
        "cover_letter_length": length,
    })

    for _ in _app.stream(None, config):
        pass

    final_state = _app.get_state(config)
    return final_state.values


def get_cover_letter_result(thread_id: str):
    """Return the CoverLetterStructured result from pipeline state, or None."""
    state = get_pipeline_state(thread_id)
    if state.get("status") == "not_found":
        return None
    return state.get("values", {}).get("cover_letter_result")
