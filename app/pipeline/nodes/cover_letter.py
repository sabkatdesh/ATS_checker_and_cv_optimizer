"""Write the cover letter from the tailored CV; invented contacts and markup are removed."""

from typing import Any

from app.domain.cv.cover_letter import CoverLetterStructured
from app.domain.cv.output_checks import scrub_contacts, strip_markup
from app.pipeline.blocks import DataTag
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.llm_call import call_step
from app.pipeline.policy import run_optional, skip_warning
from app.pipeline.state import PipelineState, RunOptions
from app.pipeline.warnings import PipelineWarning

_WORD_TARGETS = {"short": 150, "standard": 300}
_REWRITE_NOTES = {"change_log", "gaps_unaddressed"}


def _blocks(state: PipelineState) -> list[tuple[DataTag, str]]:
    cv = state["tailored_cv"]
    blocks: list[tuple[DataTag, str]] = [
        ("cv", cv.model_dump_json(exclude=_REWRITE_NOTES)),
        ("job_requirements", state["jd"].model_dump_json()),
    ]
    if cv.gaps_unaddressed:
        blocks.append(("gaps", "\n".join(f"- {gap}" for gap in cv.gaps_unaddressed)))
    return blocks


async def cover_letter(
    state: PipelineState, *, deps: PipelineDeps, ctx: RunContext
) -> dict[str, Any]:
    options = state.get("options", RunOptions())
    tone = options.cover_letter_tone or "formal"
    length = options.cover_letter_length or "standard"
    letter = await run_optional(
        "cover_letter",
        call_step(
            deps,
            ctx,
            step="cover_letter",
            schema=CoverLetterStructured,
            blocks=_blocks(state),
            task_params={"tone": tone, "length": length, "word_target": _WORD_TARGETS[length]},
        ),
    )
    if letter is None:
        return {"cover_letter": None, "warnings": [skip_warning("cover_letter")]}
    source = state.get("source_cv") or state["tailored_cv"]
    letter, removed = scrub_contacts(strip_markup(letter), source)
    if removed:
        warning = PipelineWarning(code="FOREIGN_CONTACT_REMOVED", step="cover_letter")
        return {"cover_letter": letter, "warnings": [warning]}
    return {"cover_letter": letter}
