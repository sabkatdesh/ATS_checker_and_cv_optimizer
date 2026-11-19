"""Pause for cover letter tone and length when requested but not chosen; route to generation."""

from typing import Any, Literal

from langgraph.types import interrupt

from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.state import PipelineState, RunOptions

_TONES = ("formal", "conversational")
_LENGTHS = ("short", "standard")


def _pick(value: Any, allowed: tuple[str, ...], default: str) -> str:
    return value if isinstance(value, str) and value in allowed else default


async def cover_letter_options(
    state: PipelineState, *, deps: PipelineDeps, ctx: RunContext
) -> dict[str, Any]:
    options = state.get("options", RunOptions())
    if not options.cover_letter:
        return {}
    if options.cover_letter_tone and options.cover_letter_length:
        return {}
    raw = interrupt({"type": "cover_letter_options"})
    reply = raw if isinstance(raw, dict) else {}
    updated = RunOptions.model_validate(
        {
            **options.model_dump(),
            "cover_letter_tone": _pick(reply.get("tone"), _TONES, "formal"),
            "cover_letter_length": _pick(reply.get("length"), _LENGTHS, "standard"),
        }
    )
    return {"options": updated}


def route_cover_letter(state: PipelineState) -> Literal["generate", "skip"]:
    options = state.get("options", RunOptions())
    ready = options.cover_letter and options.cover_letter_tone and options.cover_letter_length
    return "generate" if ready else "skip"
