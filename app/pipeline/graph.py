"""Pipeline graph: one async node per file, wired with deterministic routing."""

from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any, Protocol

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.nodes.ats_score import ats_score
from app.pipeline.nodes.await_answers import await_answers
from app.pipeline.nodes.cover_letter import cover_letter
from app.pipeline.nodes.cover_letter_options import cover_letter_options, route_cover_letter
from app.pipeline.nodes.cv_extract import cv_extract
from app.pipeline.nodes.eligibility import eligibility
from app.pipeline.nodes.gap_questions import gap_questions
from app.pipeline.nodes.gate import route_after_eligibility
from app.pipeline.nodes.jd_extract import jd_extract
from app.pipeline.nodes.loop_control import route_after_ats
from app.pipeline.nodes.rewrite import rewrite
from app.pipeline.state import PipelineState
from app.ports.llm import CancelToken

NodeFn = Callable[..., Awaitable[dict[str, Any]]]


class BoundNode(Protocol):
    def __call__(
        self, state: PipelineState, config: RunnableConfig
    ) -> Awaitable[dict[str, Any]]: ...


_log = structlog.get_logger("pipeline")

_NODES: dict[str, NodeFn] = {
    "jd_extract": jd_extract,
    "cv_extract": cv_extract,
    "eligibility": eligibility,
    "gap_questions": gap_questions,
    "await_answers": await_answers,
    "ats_score": ats_score,
    "rewrite": rewrite,
    "cover_letter_options": cover_letter_options,
    "cover_letter": cover_letter,
}


def _bind(name: str, fn: NodeFn, deps: PipelineDeps) -> BoundNode:
    """Adapt a node to LangGraph: a fresh RunContext per call (Task 8 swaps in the registry)."""

    async def node(state: PipelineState, config: RunnableConfig) -> dict[str, Any]:
        session_id = str(config["configurable"]["thread_id"])
        ctx = RunContext(session_id=session_id, cancel=CancelToken())
        _log.info("pipeline.stage", stage=name)
        return await fn(state, deps=deps, ctx=ctx)

    node.__name__ = name
    return node


def build_graph(deps: PipelineDeps, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    workflow = StateGraph(PipelineState)
    for name, fn in _NODES.items():
        workflow.add_node(name, _bind(name, fn, deps))

    workflow.add_edge(START, "jd_extract")
    workflow.add_edge("jd_extract", "cv_extract")
    workflow.add_edge("cv_extract", "eligibility")
    workflow.add_conditional_edges(
        "eligibility",
        route_after_eligibility,
        {"questions": "gap_questions", "ineligible": END},
    )
    workflow.add_edge("gap_questions", "await_answers")
    workflow.add_edge("await_answers", "ats_score")
    workflow.add_conditional_edges(
        "ats_score",
        partial(route_after_ats, settings=deps.settings),
        {"rewrite": "rewrite", "done": "cover_letter_options"},
    )
    workflow.add_edge("rewrite", "ats_score")
    workflow.add_conditional_edges(
        "cover_letter_options",
        route_cover_letter,
        {"generate": "cover_letter", "skip": END},
    )
    workflow.add_edge("cover_letter", END)
    return workflow.compile(checkpointer=checkpointer)
