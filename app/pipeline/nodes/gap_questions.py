"""Ask short questions that could close the eligibility gaps."""

from typing import Any

from app.domain.questions.schemas import GapQuestions
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.llm_call import call_step
from app.pipeline.state import PipelineState

MAX_QUESTIONS = 5


async def gap_questions(
    state: PipelineState, *, deps: PipelineDeps, ctx: RunContext
) -> dict[str, Any]:
    gaps = state["eligibility"].gaps_to_consider
    if not gaps:
        return {"questions": []}
    out = await call_step(
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
    )
    return {"questions": out.questions}
