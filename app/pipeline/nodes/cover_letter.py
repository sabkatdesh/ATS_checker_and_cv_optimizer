"""Write the cover letter from the tailored CV."""

from typing import Any

from app.domain.cv.cover_letter import CoverLetterStructured
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.llm_call import call_step
from app.pipeline.state import PipelineState, RunOptions

_WORD_TARGETS = {"short": 150, "standard": 300}


async def cover_letter(
    state: PipelineState, *, deps: PipelineDeps, ctx: RunContext
) -> dict[str, Any]:
    options = state.get("options", RunOptions())
    tone = options.cover_letter_tone or "formal"
    length = options.cover_letter_length or "standard"
    letter = await call_step(
        deps,
        ctx,
        step="cover_letter",
        schema=CoverLetterStructured,
        blocks=[
            ("cv", state["tailored_cv"].model_dump_json()),
            ("job_requirements", state["jd"].model_dump_json()),
        ],
        task_params={"tone": tone, "length": length, "word_target": _WORD_TARGETS[length]},
    )
    return {"cover_letter": letter}
