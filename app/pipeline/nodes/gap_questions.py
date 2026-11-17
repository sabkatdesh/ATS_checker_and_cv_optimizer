"""Ask short questions that could close the eligibility gaps."""

from typing import Any

from app.domain.questions.schemas import GapQuestions
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.llm_call import call_step
from app.pipeline.policy import run_optional, skip_warning
from app.pipeline.state import PipelineState

MAX_QUESTIONS = 5


async def gap_questions(
    state: PipelineState, *, deps: PipelineDeps, ctx: RunContext
) -> dict[str, Any]:
    gaps = state["eligibility"].gaps
    if not gaps:
        return {"questions": []}
    out = await run_optional(
        "gap_questions",
        call_step(
            deps,
            ctx,
            step="gap_questions",
            schema=GapQuestions,
            blocks=[
                ("gaps", "\n".join(f"- {g}" for g in gaps)),
                ("cv", state["source_cv"].model_dump_json()),
                ("job_requirements", state["jd"].model_dump_json()),
            ],
            task_params={"max_questions": MAX_QUESTIONS},
        ),
    )
    if out is None:
        return {"questions": [], "warnings": [skip_warning("gap_questions")]}
    return {"questions": out.questions}
