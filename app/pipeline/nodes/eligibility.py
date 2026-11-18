"""Score the candidate against the job; the threshold decision is deterministic."""

from typing import Any

from app.domain.cv.domain_reconcile import reconcile_domain
from app.domain.match.deterministic import deterministic_eligibility
from app.domain.match.schemas import Eligibility
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.llm_call import call_step
from app.pipeline.policy import run_optional, skip_warning
from app.pipeline.state import PipelineState


async def eligibility(
    state: PipelineState, *, deps: PipelineDeps, ctx: RunContext
) -> dict[str, Any]:
    cv, jd = state["source_cv"], state["jd"]
    domain = reconcile_domain(cv.domain, jd.domain).value
    verdict = await run_optional(
        "eligibility",
        call_step(
            deps,
            ctx,
            step="eligibility",
            schema=Eligibility,
            blocks=[("job_requirements", jd.model_dump_json()), ("cv", cv.model_dump_json())],
            task_params={"domain": domain},
        ),
    )
    out: dict[str, Any] = {"domain": domain}
    if verdict is None:  # unusable reply: estimate from the listed requirements instead
        verdict = deterministic_eligibility(jd, cv)
        out["warnings"] = [skip_warning("eligibility")]
    eligible = verdict.score >= deps.settings.eligibility_threshold
    return {**out, "eligibility": verdict, "eligible": eligible}
