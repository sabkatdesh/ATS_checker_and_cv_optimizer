"""A failed required step ends the session cleanly: error status, no render, no charge, no text."""

import json
import logging

import pytest
from structlog.testing import capture_logs

from app.adapters.background.inline_runner import InlineRunner
from app.config.settings import AppSettings
from app.container import Container
from app.domain.match.schemas import Eligibility
from app.pipeline.checkpoint_types import new_checkpointer
from app.pipeline.graph import build_graph
from app.pipeline.service import PipelineService
from app.ports.llm_errors import LLMOutputInvalid, LLMRefused
from app.services.generation import resume_after_answers, run_new_session
from tests.fakes.fake_auth import USER_A, FakeAuth
from tests.fakes.fake_renderers import FakeCoverLetterRenderer, FakePdfRenderer
from tests.fakes.memory_store import MemoryStore
from tests.pipeline.helpers import deps_for, persona_cv, tech_jd
from tests.pipeline.scripted_gateway import Outcome

SECRET = "SENTINEL-jd-text-do-not-log"
TID = "thread_fail"


def _container(script: dict[str, list[Outcome]]) -> Container:
    FakePdfRenderer.calls.clear()
    _, deps = deps_for(script)
    store = MemoryStore()
    store.balances[USER_A] = 5
    store.create_session(USER_A, TID, f"job description {SECRET}", cover_letter_requested=False)
    return Container(
        AppSettings(_env_file=None, env="test"),
        store=store,
        auth=FakeAuth(),
        pipeline=PipelineService(build_graph(deps, new_checkpointer())),
        runner=InlineRunner(),
        pdf_factory=FakePdfRenderer,
        cover_letter_factory=FakeCoverLetterRenderer,
    )


def _start(c: Container) -> None:
    run_new_session(
        c,
        user_id=USER_A,
        thread_id=TID,
        profile={"full_name": "Test Person"},
        job_description=f"job description {SECRET}",
        cover_letter=False,
        cover_letter_tone=None,
        cover_letter_length=None,
    )


def _script(rewrite: list[Outcome], gaps: list[str] | None = None) -> dict[str, list[Outcome]]:
    return {
        "jd_extract": [tech_jd()],
        "cv_extract": [persona_cv()],
        "eligibility": [Eligibility(score=60, gaps=gaps or [])],
        "rewrite": rewrite,
    }


def test_rewrite_failure_never_renders_empty_cv():
    c = _container(_script([LLMOutputInvalid(f"bad reply {SECRET}")]))
    _start(c)
    assert c.store.get_session(TID)["status"] == "error"
    assert FakePdfRenderer.calls == []
    summary = c.pipeline.summary(TID)
    assert summary is not None and summary.error_code == "LLM_OUTPUT_INVALID"
    assert c.store.get_coin_balance(USER_A) == 5
    assert not [call for call in c.store.calls if call[0] == "deduct_coins"]  # type: ignore[attr-defined]


def test_failure_after_answers_is_also_an_error_session():
    from app.domain.questions.schemas import GapQuestion, GapQuestions

    script = _script([LLMRefused("x")], gaps=["Kubernetes"])
    script["gap_questions"] = [GapQuestions(questions=[GapQuestion(id="q1", text="K8s?")])]
    c = _container(script)
    _start(c)
    assert c.store.get_session(TID)["status"] == "awaiting_hitl"
    resume_after_answers(c, user_id=USER_A, thread_id=TID, reply="my private answer")
    assert c.store.get_session(TID)["status"] == "error"
    assert FakePdfRenderer.calls == []
    summary = c.pipeline.summary(TID)
    assert summary is not None and summary.error_code == "CONTENT_REFUSED"
    assert c.store.get_coin_balance(USER_A) == 5


def test_no_text_in_error_logs(caplog: pytest.LogCaptureFixture):
    c = _container(_script([LLMOutputInvalid(f"bad reply {SECRET}")]))
    with caplog.at_level(logging.DEBUG), capture_logs() as logs:
        _start(c)
    assert any(e["event"] == "pipeline.failed" and e["code"] == "LLM_OUTPUT_INVALID" for e in logs)
    assert SECRET not in json.dumps(logs, default=str)
    assert SECRET not in caplog.text
    summary = c.pipeline.summary(TID)
    assert summary is not None and SECRET not in summary.model_dump_json()
