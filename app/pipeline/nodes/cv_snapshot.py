"""Take the saved profile as the source CV: deterministic conversion, no LLM call."""

from typing import Any

from app.domain.cv.profile_to_cv import profile_to_universal_cv
from app.domain.jd.markers import find_markers
from app.domain.text.invisible import strip_invisible
from app.domain.text.strings import iter_strings, map_strings
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.state import PipelineState
from app.pipeline.warnings import PipelineWarning, WarningCode

STEP = "cv_snapshot"


async def cv_snapshot(
    state: PipelineState, *, deps: PipelineDeps, ctx: RunContext
) -> dict[str, Any]:
    conversion = profile_to_universal_cv(state["profile"])
    cv = map_strings(conversion.cv, strip_invisible)
    codes: list[WarningCode] = []
    if find_markers("\n".join(text for _, text in iter_strings(cv))):
        codes.append("CV_INJECTION_MARKERS")
    if conversion.dropped_entries:
        codes.append("PROFILE_ENTRY_INVALID")
    if conversion.unknown_keys:
        codes.append("UNKNOWN_PROFILE_KEYS")
    return {
        "source_cv": cv,
        "domain": cv.domain.value,
        "warnings": [PipelineWarning(code=code, step=STEP) for code in codes],
    }
