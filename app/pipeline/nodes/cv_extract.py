"""Transitional: structure the CV text with the LLM (replaced by cv_snapshot in Task 9)."""

from typing import Any

from app.domain.cv.domain_config import Domain
from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.jd.markers import find_markers
from app.domain.text.invisible import strip_invisible
from app.domain.text.strings import map_strings
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.llm_call import call_step
from app.pipeline.policy import run_required
from app.pipeline.state import PipelineState
from app.pipeline.warnings import PipelineWarning


async def cv_extract(
    state: PipelineState, *, deps: PipelineDeps, ctx: RunContext
) -> dict[str, Any]:
    jd = state.get("jd")
    domain = jd.domain.value if jd is not None else Domain.GENERAL.value
    cv_text = strip_invisible(state["cv_text"])
    cv = await run_required(
        "cv_extract",
        call_step(
            deps,
            ctx,
            step="cv_extract",
            schema=UniversalCVStructured,
            blocks=[("cv", cv_text)],
            task_params={"domain": domain},
        ),
    )
    out: dict[str, Any] = {"source_cv": map_strings(cv, strip_invisible)}
    if find_markers(cv_text):
        out["warnings"] = [PipelineWarning(code="CV_INJECTION_MARKERS", step="cv_extract")]
    return out
