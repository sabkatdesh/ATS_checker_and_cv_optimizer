"""Deterministic ATS score of the current CV (tailored if present, else the source)."""

from typing import Any

import structlog

from app.domain.ats.checker import compute_final_match
from app.domain.cv.domain_config import should_run_ats
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.errors import PipelineStepFailed
from app.pipeline.state import PipelineState

_log = structlog.get_logger("pipeline")


def _simplified() -> dict[str, Any]:
    """Non-ATS domains: score 100 means nothing to optimise for keyword scanners."""
    return {"overall_score": 100, "section_scores": {}, "hard_gaps": [], "rewrite_hints": {}}


async def ats_score(state: PipelineState, *, deps: PipelineDeps, ctx: RunContext) -> dict[str, Any]:
    cv = state.get("tailored_cv") or state["source_cv"]
    if not should_run_ats(state["domain"]):
        match = _simplified()
    else:
        try:
            match = compute_final_match(state["jd"], cv)
        except Exception as exc:  # a scorer bug must fail the job, never fake a score
            _log.error("pipeline.ats_failed", error_type=type(exc).__name__)
            raise PipelineStepFailed("ats_score", "INTERNAL") from None
    out: dict[str, Any] = {"ats": match}
    if "ats_before" not in state:
        out["ats_before"] = match
    return out
