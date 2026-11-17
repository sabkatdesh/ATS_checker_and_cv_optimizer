"""Score the candidate against the job; the threshold decision is deterministic."""

from typing import Any

from app.domain.cv.domain_config import Domain
from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.jd.schemas import JobDescriptionStructured
from app.domain.match.schemas import Match
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.llm_call import call_step
from app.pipeline.state import PipelineState


def reconcile_domain(cv: UniversalCVStructured, jd: JobDescriptionStructured) -> str:
    """CV domain wins (the candidate knows their profession), then the JD domain, then general."""
    for domain in (cv.domain, jd.domain):
        if domain != Domain.GENERAL:
            return domain.value
    return Domain.GENERAL.value


async def eligibility(
    state: PipelineState, *, deps: PipelineDeps, ctx: RunContext
) -> dict[str, Any]:
    cv, jd = state["source_cv"], state["jd"]
    domain = reconcile_domain(cv, jd)
    verdict = await call_step(
        deps,
        ctx,
        step="eligibility",
        schema=Match,
        blocks=[("job_requirements", jd.model_dump_json()), ("cv", cv.model_dump_json())],
        task_params={"domain": domain},
    )
    eligible = (verdict.score or 0) >= deps.settings.eligibility_threshold
    return {"domain": domain, "eligibility": verdict, "eligible": eligible}
