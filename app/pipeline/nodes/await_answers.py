"""Pause once for the candidate's answers; empty or skipped replies proceed, never re-ask."""

from typing import Any

from langgraph.types import interrupt

from app.domain.questions.reply import normalise_reply
from app.domain.questions.schemas import GapAnswers
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.state import PipelineState


async def await_answers(
    state: PipelineState, *, deps: PipelineDeps, ctx: RunContext
) -> dict[str, Any]:
    questions = state.get("questions") or []
    if not questions:
        return {"answers": GapAnswers(skipped=True)}
    raw = interrupt(
        {"type": "gap_questions", "questions": [q.model_dump(mode="json") for q in questions]}
    )
    return {"answers": normalise_reply(raw, questions)}
