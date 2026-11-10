"""Pipeline graph: wires all nodes into the LangGraph StateGraph."""

from functools import partial

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.pipeline.chains import Chains
from app.pipeline.nodes.cover_letter import (
    check_cover_letter_gate,
    cover_letter_hitl_node,
    generate_cover_letter_node,
)
from app.pipeline.nodes.detailed import (
    check_ats_score,
    compute_match,
    detailed_extract_cv,
    detailed_extract_jd,
    start_detailed_phase,
)
from app.pipeline.nodes.eligibility import (
    check_eligibility_gate,
    eligibility_check,
    quick_extract_cv,
    quick_extract_jd,
)
from app.pipeline.nodes.hitl import hitl_node
from app.pipeline.nodes.rewrite import rewrite_cv_node
from app.pipeline.state import CombinedState


def build_graph(chains: Chains, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    workflow = StateGraph(CombinedState)

    workflow.add_node("quick_extract_jd", partial(quick_extract_jd, chains=chains))
    workflow.add_node("quick_extract_cv", partial(quick_extract_cv, chains=chains))
    workflow.add_node("eligibility_check", partial(eligibility_check, chains=chains))
    workflow.add_node("hitl_node", hitl_node)
    workflow.add_node("start_detailed_phase", start_detailed_phase)
    workflow.add_node("detailed_extract_jd", partial(detailed_extract_jd, chains=chains))
    workflow.add_node("detailed_extract_cv", partial(detailed_extract_cv, chains=chains))
    workflow.add_node("compute_match", compute_match)
    workflow.add_node("rewrite_cv", partial(rewrite_cv_node, chains=chains))
    workflow.add_node("cover_letter_hitl", cover_letter_hitl_node)
    workflow.add_node("generate_cover_letter", partial(generate_cover_letter_node, chains=chains))

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

    return workflow.compile(checkpointer=checkpointer)
