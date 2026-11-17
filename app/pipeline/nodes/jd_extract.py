"""Structure the job description."""

from typing import Any

from app.domain.jd.schemas import JobDescriptionStructured
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.llm_call import call_step
from app.pipeline.policy import run_required
from app.pipeline.state import PipelineState


async def jd_extract(
    state: PipelineState, *, deps: PipelineDeps, ctx: RunContext
) -> dict[str, Any]:
    jd = await run_required(
        "jd_extract",
        call_step(
            deps,
            ctx,
            step="jd_extract",
            schema=JobDescriptionStructured,
            blocks=[("job_description", state["jd_text"])],
        ),
    )

    return {"jd": jd}
