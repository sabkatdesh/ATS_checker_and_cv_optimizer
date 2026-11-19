"""Deterministic rewrite loop control: the LLM never decides when to stop."""

from typing import Literal

from app.config.pipeline_settings import PipelineSettings
from app.domain.cv.domain_config import Domain, should_run_ats
from app.pipeline.state import PipelineState, RunOptions


def route_after_ats(
    state: PipelineState, *, settings: PipelineSettings
) -> Literal["rewrite", "done"]:
    passes = state.get("passes", 0)
    if passes == 0:
        return "rewrite"
    if not should_run_ats(state.get("domain", Domain.GENERAL.value)):
        return "done"
    if (state["ats"].score or 0) >= settings.ats_target:
        return "done"
    if passes >= state.get("options", RunOptions()).max_passes:
        return "done"
    return "rewrite"
