"""Pipeline graph: one async node per file, wired with deterministic routing."""

from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any, Protocol

import structlog
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.config import get_config
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.pipeline.deps import PipelineDeps
from app.pipeline.errors import PipelineCancelled
from app.pipeline.hooks import NODE_STAGES, Phase, ProgressEvent
from app.pipeline.nodes.ats_score import ats_score
from app.pipeline.nodes.await_answers import await_answers
from app.pipeline.nodes.cover_letter import cover_letter
from app.pipeline.nodes.cover_letter_options import cover_letter_options, route_cover_letter
from app.pipeline.nodes.cv_snapshot import cv_snapshot
from app.pipeline.nodes.eligibility import eligibility
from app.pipeline.nodes.gap_questions import gap_questions
from app.pipeline.nodes.gate import route_after_eligibility
from app.pipeline.nodes.jd_extract import jd_extract
from app.pipeline.nodes.loop_control import route_after_ats
from app.pipeline.nodes.revise_flagged import revise_flagged
from app.pipeline.nodes.rewrite import rewrite
from app.pipeline.nodes.verify_claims import route_after_verify, verify_claims
from app.pipeline.state import PipelineState
from app.ports.llm_errors import LLMCancelled

NodeFn = Callable[..., Awaitable[dict[str, Any]]]


class BoundNode(Protocol):
    def __call__(self, state: PipelineState) -> Awaitable[dict[str, Any]]: ...


_log = structlog.get_logger("pipeline")

_NODES: dict[str, NodeFn] = {
    "jd_extract": jd_extract,
    "cv_snapshot": cv_snapshot,
    "eligibility": eligibility,
    "gap_questions": gap_questions,
    "await_answers": await_answers,
    "ats_score": ats_score,
    "rewrite": rewrite,
    "verify_claims": verify_claims,
    "revise_flagged": revise_flagged,
    "cover_letter_options": cover_letter_options,
    "cover_letter": cover_letter,
}


async def _notify(hook: Callable[[ProgressEvent], Awaitable[None]], event: ProgressEvent) -> None:
    """Progress can never break a run: a failing hook is logged (no event payload) and ignored."""
    try:
        await hook(event)
    except Exception as exc:  # noqa: BLE001 - any hook failure is swallowed by design
        _log.warning(
            "pipeline.hook_failed", node=event.node, phase=event.phase, error=type(exc).__name__
        )


def _bind(name: str, fn: NodeFn, deps: PipelineDeps) -> BoundNode:
    """Adapt a node to LangGraph: the run's context, cancel checkpoints and progress hooks.

    A cancel seen after the node ran discards its update (nothing is committed), so a resume
    re-runs the node.
    """
    stage, percent = NODE_STAGES[name]

    async def node(state: PipelineState) -> dict[str, Any]:
        ctx = deps.runs.get(str(get_config()["configurable"]["thread_id"]))
        if ctx.cancel.is_cancelled:
            raise PipelineCancelled(name, stage, "before")

        def event(phase: Phase) -> ProgressEvent:
            progress = ctx.progress.advance(percent)
            return ProgressEvent(ctx.session_id, name, stage, phase, progress)

        await _notify(ctx.hooks.before_node, event("started"))
        _log.info("pipeline.stage", stage=name)
        try:
            update = await fn(state, deps=deps, ctx=ctx)
        except LLMCancelled:
            raise PipelineCancelled(name, stage, "during") from None
        await _notify(ctx.hooks.after_node, event("finished"))
        if ctx.cancel.is_cancelled:
            raise PipelineCancelled(name, stage, "after")
        return update

    node.__name__ = name
    return node


def build_state_graph(deps: PipelineDeps) -> StateGraph:
    """The uncompiled graph; PipelineService compiles it with each run's checkpointer."""
    workflow = StateGraph(PipelineState)
    for name, fn in _NODES.items():
        workflow.add_node(name, _bind(name, fn, deps))

    workflow.add_edge(START, "jd_extract")
    workflow.add_edge("jd_extract", "cv_snapshot")
    workflow.add_edge("cv_snapshot", "eligibility")
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
        {"rewrite": "rewrite", "done": "verify_claims"},
    )
    workflow.add_edge("rewrite", "ats_score")
    workflow.add_conditional_edges(
        "verify_claims",
        route_after_verify,
        {"revise": "revise_flagged", "done": "cover_letter_options"},
    )
    workflow.add_edge("revise_flagged", "verify_claims")
    workflow.add_conditional_edges(
        "cover_letter_options",
        route_cover_letter,
        {"generate": "cover_letter", "skip": END},
    )
    workflow.add_edge("cover_letter", END)
    return workflow


def build_graph(deps: PipelineDeps, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    return build_state_graph(deps).compile(checkpointer=checkpointer)
