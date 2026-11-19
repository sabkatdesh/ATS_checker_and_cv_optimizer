import asyncio

import pytest

from app.pipeline.errors import PipelineStepFailed
from app.pipeline.policy import POLICY, run_optional, run_required, to_step_failure
from app.ports.llm_errors import (
    LLMAllRoutesFailed,
    LLMAuthError,
    LLMBadRequest,
    LLMCancelled,
    LLMCircuitOpen,
    LLMError,
    LLMOutputInvalid,
    LLMOutputTruncated,
    LLMRefused,
    LLMThrottled,
    LLMTimeout,
    LLMUnavailable,
)

CODES = [
    (LLMOutputInvalid, "LLM_OUTPUT_INVALID"),
    (LLMOutputTruncated, "LLM_OUTPUT_INVALID"),
    (LLMRefused, "CONTENT_REFUSED"),
    (LLMUnavailable, "LLM_UNAVAILABLE"),
    (LLMTimeout, "LLM_UNAVAILABLE"),
    (LLMThrottled, "LLM_UNAVAILABLE"),
    (LLMCircuitOpen, "LLM_UNAVAILABLE"),
    (LLMAllRoutesFailed, "LLM_UNAVAILABLE"),
    (LLMBadRequest, "LLM_BAD_REQUEST"),
    (LLMAuthError, "LLM_AUTH"),
    (LLMError, "INTERNAL"),
]


@pytest.mark.parametrize(("kind", "code"), CODES)
def test_error_class_maps_to_code(kind, code):
    failure = to_step_failure("rewrite", kind("x"))
    assert (failure.step, failure.code, failure.refund) == ("rewrite", code, "SYSTEM")
    assert str(failure) == f"rewrite failed: {code}"


def test_failure_text_is_constant():
    failure = to_step_failure("rewrite", LLMOutputInvalid("SENTINEL in the detail"))
    assert "SENTINEL" not in str(failure) + repr(failure)


def test_policy_table():
    required = {"jd_extract", "rewrite", "revise_flagged"}
    assert {s for s, v in POLICY.items() if v == "required"} == required
    optional = {"eligibility", "gap_questions", "verify_claims", "cover_letter"}
    assert {s for s, v in POLICY.items() if v == "optional"} == optional


async def _raise(err: Exception) -> str:
    raise err


def _optional(step: str, err: LLMError) -> str | None:
    return asyncio.run(run_optional(step, _raise(err)))


def test_required_passes_a_result_through():
    async def ok() -> str:
        return "fine"

    assert asyncio.run(run_required("rewrite", ok())) == "fine"


def test_required_reraises_cancellation_untouched():
    with pytest.raises(LLMCancelled):
        asyncio.run(run_required("rewrite", _raise(LLMCancelled("c"))))


def test_cancellation_is_never_skipped():
    with pytest.raises(LLMCancelled):
        _optional("cover_letter", LLMCancelled("c"))


def test_gap_questions_skips_only_invalid_output():
    assert _optional("gap_questions", LLMOutputInvalid("x")) is None
    assert _optional("gap_questions", LLMOutputTruncated("x")) is None
    for err, code in [
        (LLMRefused("x"), "CONTENT_REFUSED"),
        (LLMUnavailable("x"), "LLM_UNAVAILABLE"),
        (LLMTimeout("x"), "LLM_UNAVAILABLE"),
    ]:
        with pytest.raises(PipelineStepFailed) as exc:
            _optional("gap_questions", err)
        assert exc.value.code == code


def test_cover_letter_skips_invalid_output_and_infrastructure_failures():
    for err in (LLMOutputInvalid("x"), LLMUnavailable("x"), LLMTimeout("x"), LLMThrottled("x")):
        assert _optional("cover_letter", err) is None
    with pytest.raises(PipelineStepFailed) as exc:
        _optional("cover_letter", LLMRefused("x"))
    assert exc.value.code == "CONTENT_REFUSED"
    with pytest.raises(PipelineStepFailed) as exc:
        _optional("cover_letter", LLMAuthError("x"))
    assert exc.value.code == "LLM_AUTH"


def test_verify_claims_judge_skips_on_any_llm_failure_but_cancellation():
    for err in (LLMOutputInvalid("x"), LLMRefused("x"), LLMUnavailable("x"), LLMAuthError("x")):
        assert _optional("verify_claims", err) is None
    with pytest.raises(LLMCancelled):
        _optional("verify_claims", LLMCancelled("c"))


def test_revise_flagged_skips_only_invalid_output():
    assert _optional("revise_flagged", LLMOutputInvalid("x")) is None
    assert _optional("revise_flagged", LLMOutputTruncated("x")) is None
    with pytest.raises(PipelineStepFailed) as exc:
        _optional("revise_flagged", LLMUnavailable("x"))
    assert (exc.value.step, exc.value.code) == ("revise_flagged", "LLM_UNAVAILABLE")
