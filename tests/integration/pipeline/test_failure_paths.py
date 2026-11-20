"""A failed required step ends the session cleanly: error status, no render, no charge, no text."""

import json
import logging

import pytest
from structlog.testing import capture_logs

from app.adapters.background.inline_runner import InlineRunner
from app.config.settings import AppSettings
from app.container import Container
from app.domain.match.schemas import Eligibility
from app.pipeline.checkpointer import MemoryCheckpointerFactory
from app.pipeline.graph import build_state_graph
from app.pipeline.service import PipelineService
from app.ports.llm_errors import LLMOutputInvalid, LLMRefused
from app.services.generation import resume_after_answers, run_new_session
from tests.fakes.backend import backend_with_session, legacy_status_of
from tests.fakes.fake_auth import USER_A
from tests.fakes.fake_renderers import FakeCoverLetterRenderer, FakePdfRenderer
from tests.pipeline.helpers import deps_for, persona_profile, tech_jd
from tests.pipeline.scripted_gateway import Outcome

SECRET = "SENTINEL-jd-text-do-not-log"
TID = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a01"


def _container(script: dict[str, list[Outcome]]) -> Container:
    FakePdfRenderer.calls.clear()
    _, deps = deps_for(script)
    backend = backend_with_session(USER_A, TID, f"job description {SECRET}")
    return Container(
        AppSettings(_env_file=None, env="test"),
        **backend.repos(),
        pipeline=PipelineService(build_state_graph(deps), deps.runs, MemoryCheckpointerFactory()),
        runner=InlineRunner(),
        pdf_factory=FakePdfRenderer,
        cover_letter_factory=FakeCoverLetterRenderer,
    )


def _start(c: Container) -> None:
    run_new_session(
        c,
        user_id=USER_A,
        thread_id=TID,
        profile=persona_profile(),
        job_description=f"job description {SECRET}",
        cover_letter=False,
        cover_letter_tone=None,
        cover_letter_length=None,
    )


def _script(rewrite: list[Outcome], gaps: list[str] | None = None) -> dict[str, list[Outcome]]:
    return {
        "jd_extract": [tech_jd()],
        "eligibility": [Eligibility(score=60, gaps=gaps or [])],
        "rewrite": rewrite,
    }


def test_rewrite_failure_never_renders_empty_cv():
    c = _container(_script([LLMOutputInvalid(f"bad reply {SECRET}")]))
    _start(c)
    assert legacy_status_of(c.sessions, USER_A, TID) == "error"
    assert FakePdfRenderer.calls == []
    summary = c.pipeline.summary(TID)
    assert summary is not None and summary.error_code == "LLM_OUTPUT_INVALID"
    assert c.credits.ledger(USER_A) == []


def test_failure_after_answers_is_also_an_error_session():
    from app.domain.questions.schemas import GapQuestion, GapQuestions

    script = _script([LLMRefused("x")], gaps=["Kubernetes"])
    script["gap_questions"] = [GapQuestions(questions=[GapQuestion(id="q1", text="K8s?")])]
    c = _container(script)
    _start(c)
    assert legacy_status_of(c.sessions, USER_A, TID) == "awaiting_hitl"
    resume_after_answers(c, user_id=USER_A, thread_id=TID, reply="my private answer")
    assert legacy_status_of(c.sessions, USER_A, TID) == "error"
    assert FakePdfRenderer.calls == []
    summary = c.pipeline.summary(TID)
    assert summary is not None and summary.error_code == "CONTENT_REFUSED"
    assert c.credits.ledger(USER_A) == []


def test_no_text_in_error_logs(caplog: pytest.LogCaptureFixture):
    c = _container(_script([LLMOutputInvalid(f"bad reply {SECRET}")]))
    with caplog.at_level(logging.DEBUG), capture_logs() as logs:
        _start(c)
    assert any(e["event"] == "pipeline.failed" and e["code"] == "LLM_OUTPUT_INVALID" for e in logs)
    assert SECRET not in json.dumps(logs, default=str)
    assert SECRET not in caplog.text
    summary = c.pipeline.summary(TID)
    assert summary is not None and SECRET not in summary.model_dump_json()
