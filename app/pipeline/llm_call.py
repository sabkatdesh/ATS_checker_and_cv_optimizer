"""The one place a pipeline step calls the LLM gateway."""

from collections.abc import Mapping, Sequence
from typing import Any, cast

import structlog
from pydantic import BaseModel

from app.pipeline.blocks import DataTag, user_message
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.ports.llm import CallMeta, LLMRequest, Message

_log = structlog.get_logger("pipeline")


async def call_step[T: BaseModel](
    deps: PipelineDeps,
    ctx: RunContext,
    *,
    step: str,
    schema: type[T],
    blocks: Sequence[tuple[DataTag, str]],
    task_params: Mapping[str, int | float | str] | None = None,
    cache_prefix: bool = False,
) -> T:
    prompt = deps.prompts.get(step)
    content = user_message(blocks, prompt.task_line(**(task_params or {})))
    req: LLMRequest[Any] = LLMRequest(
        step=step,
        system=prompt.system,
        messages=[Message(role="user", content=content)],
        output_schema=schema,
        cache_prefix=cache_prefix,
        metadata=CallMeta(prompt_id=step, prompt_version=prompt.version, session_id=ctx.session_id),
    )
    result = await deps.gateway.complete(req, ctx.cancel)
    _log.info(
        "pipeline.llm_call",
        step=step,
        prompt_version=prompt.version,
        cost_usd=float(result.cost_usd),
        repaired=result.repaired,
        attempts=result.attempts,
    )
    return cast(T, result.output)
