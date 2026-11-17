"""Pause for the candidate's answers when there are questions (normalised in Task 4)."""

from typing import Any

from langgraph.types import interrupt

from app.domain.questions.schemas import GapAnswers
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.state import PipelineState


async def await_answers(
    state: PipelineState, *, deps: PipelineDeps, ctx: RunContext
) -> dict[str, Any]:
    questions = state.get("questions") or []
    if not questions:
        return {}
    raw = interrupt(
        {"type": "gap_questions", "questions": [q.model_dump(mode="json") for q in questions]}
    )
    return {"answers": GapAnswers(free_text=str(raw or ""))}
