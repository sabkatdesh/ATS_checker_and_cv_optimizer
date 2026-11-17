"""What each LLM step does when its call fails (spec 10 section 2, 08 A4-A6)."""

from collections.abc import Awaitable
from typing import Literal

import structlog

from app.pipeline.errors import ErrorCode, PipelineStepFailed
from app.pipeline.warnings import PipelineWarning, WarningCode
from app.ports.llm_errors import (
    LLMAuthError,
    LLMBadRequest,
    LLMCancelled,
    LLMError,
    LLMOutputInvalid,
    LLMRefused,
    LLMThrottled,
    LLMTimeout,
    LLMUnavailable,
)

_log = structlog.get_logger("pipeline")

POLICY: dict[str, Literal["required", "optional"]] = {
    "jd_extract": "required",
    "cv_extract": "required",
    "eligibility": "required",  # Task 3 swaps this for the deterministic fallback
    "rewrite": "required",
    "gap_questions": "optional",
    "cover_letter": "optional",
}

_INFRA = (LLMUnavailable, LLMTimeout, LLMThrottled)

# Optional steps skip (with a warning) only on these failures; anything else fails the job.
_SKIP_ON: dict[str, tuple[type[LLMError], ...]] = {
    "gap_questions": (LLMOutputInvalid,),
    "cover_letter": (LLMOutputInvalid, *_INFRA),
}
_SKIP_WARNING: dict[str, WarningCode] = {
    "gap_questions": "QUESTIONS_SKIPPED",
    "cover_letter": "COVER_LETTER_SKIPPED",
}

_CODES: tuple[tuple[type[LLMError], ErrorCode], ...] = (
    (LLMRefused, "CONTENT_REFUSED"),
    (LLMOutputInvalid, "LLM_OUTPUT_INVALID"),  # includes LLMOutputTruncated
    (LLMBadRequest, "LLM_BAD_REQUEST"),
    (LLMAuthError, "LLM_AUTH"),
    (LLMUnavailable, "LLM_UNAVAILABLE"),  # includes circuit-open and all-routes-failed
    (LLMTimeout, "LLM_UNAVAILABLE"),
    (LLMThrottled, "LLM_UNAVAILABLE"),
)


def to_step_failure(step: str, err: LLMError) -> PipelineStepFailed:
    code: ErrorCode = "INTERNAL"
    for kind, mapped in _CODES:
        if isinstance(err, kind):
            code = mapped
            break
    return PipelineStepFailed(step, code)


def skip_warning(step: str) -> PipelineWarning:
    return PipelineWarning(code=_SKIP_WARNING[step], step=step)


async def run_required[R](step: str, call: Awaitable[R]) -> R:
    """Await a step's LLM call; any LLM failure ends the job with a typed code."""
    try:
        return await call
    except LLMCancelled:
        raise
    except LLMError as err:
        failure = to_step_failure(step, err)
        _log.warning("pipeline.step_failed", step=step, code=failure.code, kind=err.kind)
        raise failure from None


async def run_optional[R](step: str, call: Awaitable[R]) -> R | None:
    """Like run_required, but returns None where the policy allows the step to be skipped."""
    try:
        return await call
    except LLMCancelled:
        raise
    except LLMError as err:
        if isinstance(err, _SKIP_ON.get(step, ())):
            _log.warning("pipeline.step_skipped", step=step, kind=err.kind)
            return None
        failure = to_step_failure(step, err)
        _log.warning("pipeline.step_failed", step=step, code=failure.code, kind=err.kind)
        raise failure from None
