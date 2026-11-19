"""Sanitise and structure the job description; injection markers become a warning."""

from typing import Any

from app.domain.jd.meta import normalise_jd
from app.domain.jd.sanitize import sanitize_jd
from app.domain.jd.schemas import JobDescriptionStructured
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.llm_call import call_step
from app.pipeline.policy import run_required
from app.pipeline.state import PipelineState
from app.pipeline.warnings import PipelineWarning


async def jd_extract(
    state: PipelineState, *, deps: PipelineDeps, ctx: RunContext
) -> dict[str, Any]:
    clean = sanitize_jd(state["jd_text"])
    jd = await run_required(
        "jd_extract",
        call_step(
            deps,
            ctx,
            step="jd_extract",
            schema=JobDescriptionStructured,
            blocks=[("job_description", clean.text)],
        ),
    )
    out: dict[str, Any] = {"jd": normalise_jd(jd, clean.text)}
    if clean.markers:
        out["warnings"] = [PipelineWarning(code="JD_INJECTION_MARKERS", step="jd_extract")]
    return out
