"""Pasted CV text to a structured profile, through the LLM gateway.

Failures are typed with a constant message; an invalid, truncated or empty reply is an error,
never an empty profile.
"""

from typing import Any, Literal, cast

import structlog

from app.domain.cv.domain_config import Domain
from app.domain.cv.profile_text import ProfileBuilder
from app.domain.cv.universal_cv import UniversalCVStructured
from app.pipeline.blocks import user_message
from app.pipeline.prompts.loader import PromptLibrary
from app.ports.llm import CallMeta, LLMGateway, LLMRequest, Message
from app.ports.llm_errors import LLMError, LLMOutputInvalid, LLMRefused

STEP = "profile_import"

ImportErrorCode = Literal["CV_IMPORT_FAILED", "CONTENT_REFUSED", "LLM_UNAVAILABLE"]

_log = structlog.get_logger("profile_import")


class ProfileImportFailed(Exception):
    """The CV could not be imported; `code` says why. The message never carries CV text."""

    def __init__(self, code: ImportErrorCode) -> None:
        self.code: ImportErrorCode = code
        super().__init__(f"{STEP} failed: {code}")


def _code(err: LLMError) -> ImportErrorCode:
    if isinstance(err, LLMRefused):
        return "CONTENT_REFUSED"
    if isinstance(err, LLMOutputInvalid):  # includes LLMOutputTruncated
        return "CV_IMPORT_FAILED"
    return "LLM_UNAVAILABLE"  # unavailable, timeout, throttled, auth, bad request


async def import_profile(
    gateway: LLMGateway, prompts: PromptLibrary, cv_text: str
) -> UniversalCVStructured:
    prompt = prompts.get(STEP)
    req: LLMRequest[Any] = LLMRequest(
        step=STEP,
        system=prompt.system,
        messages=[Message(role="user", content=user_message([("cv", cv_text)], prompt.task))],
        output_schema=UniversalCVStructured,
        metadata=CallMeta(prompt_id=STEP, prompt_version=prompt.version),
    )
    try:
        result = await gateway.complete(req)
    except LLMError as err:
        code = _code(err)
        _log.warning("profile_import.failed", code=code, kind=err.kind, length=len(cv_text))
        raise ProfileImportFailed(code) from None
    profile = cast(UniversalCVStructured, result.output)
    if not profile.model_dump(exclude_defaults=True, exclude={"domain"}):
        _log.warning("profile_import.failed", code="CV_IMPORT_FAILED", kind="empty")
        raise ProfileImportFailed("CV_IMPORT_FAILED")
    if profile.domain == Domain.GENERAL:
        detected = ProfileBuilder.detect_domain(profile.model_dump())
        profile = profile.model_copy(update={"domain": detected})
    return profile
