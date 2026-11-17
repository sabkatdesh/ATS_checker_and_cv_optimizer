"""Transitional: structure the CV text with the LLM (replaced by cv_snapshot in Task 9)."""

from typing import Any

from app.domain.cv.domain_config import Domain
from app.domain.cv.universal_cv import UniversalCVStructured
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.llm_call import call_step
from app.pipeline.policy import run_required
from app.pipeline.state import PipelineState


async def cv_extract(
    state: PipelineState, *, deps: PipelineDeps, ctx: RunContext
) -> dict[str, Any]:
    jd = state.get("jd")
    domain = jd.domain.value if jd is not None else Domain.GENERAL.value
    cv = await run_required(
        "cv_extract",
        call_step(
            deps,
            ctx,
            step="cv_extract",
            schema=UniversalCVStructured,
            blocks=[("cv", state["cv_text"])],
            task_params={"domain": domain},
        ),
    )

    return {"source_cv": cv}
