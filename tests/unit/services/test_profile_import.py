"""Profile import on the LLM gateway: typed failures, never an empty profile."""

import asyncio

import pytest

from app.config.settings import AppSettings
from app.container import Container
from app.domain.cv.universal_cv import UniversalCVStructured
from app.pipeline.prompts.loader import PromptLibrary
from app.ports.llm_errors import (
    LLMAuthError,
    LLMOutputInvalid,
    LLMOutputTruncated,
    LLMRefused,
    LLMThrottled,
    LLMUnavailable,
)
from app.services.profile_import import ProfileImportFailed, import_profile
from tests.pipeline.scripted_gateway import ScriptedGateway

CV = "Registered nurse. Ward experience at City Hospital since 2019. " * 3


def _run(gateway, text: str = CV) -> UniversalCVStructured:
    return asyncio.run(import_profile(gateway, PromptLibrary(), text))


def test_import_valid_on_fake_provider():
    c = Container(AppSettings(_env_file=None, env="test", llm={"default_provider": "fake"}))
    profile = _run(c.llm)
    assert profile.domain.value == "tech"
    assert profile.meta.full_name == "Jane Example"


def test_import_cv_text_in_data_block():
    out = UniversalCVStructured(domain="medical", professional_summary="Ward nurse.")
    gw = ScriptedGateway({"profile_import": [out]})
    _run(gw)
    req = gw.requests[0]
    assert CV not in (req.system or "")
    assert f"<cv>\n{CV}\n</cv>" in req.messages[0].content
    assert req.metadata.prompt_id == "profile_import"
    assert req.output_schema is UniversalCVStructured


def test_general_domain_is_detected():
    out = UniversalCVStructured(
        domain="general",
        professional_summary="Registered nurse working in a hospital ward caring for patients.",
    )
    assert _run(ScriptedGateway({"profile_import": [out]})).domain.value == "medical"


@pytest.mark.parametrize(
    ("err", "code"),
    [
        (LLMOutputTruncated("truncated"), "CV_IMPORT_FAILED"),
        (LLMOutputInvalid("invalid"), "CV_IMPORT_FAILED"),
        (LLMRefused("refused"), "CONTENT_REFUSED"),
        (LLMUnavailable("down"), "LLM_UNAVAILABLE"),
        (LLMThrottled("slow"), "LLM_UNAVAILABLE"),
        (LLMAuthError("auth"), "LLM_UNAVAILABLE"),
    ],
)
def test_llm_errors_become_typed_failures(err, code):
    with pytest.raises(ProfileImportFailed) as info:
        _run(ScriptedGateway({"profile_import": [err]}))
    assert info.value.code == code
    assert CV not in str(info.value)


@pytest.mark.parametrize("domain", ["general", "tech"])
def test_empty_profile_is_import_failed(domain):
    empty = UniversalCVStructured(domain=domain)
    with pytest.raises(ProfileImportFailed) as info:
        _run(ScriptedGateway({"profile_import": [empty]}))
    assert info.value.code == "CV_IMPORT_FAILED"
