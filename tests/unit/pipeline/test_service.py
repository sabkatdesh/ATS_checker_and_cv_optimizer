import json
import os
import re
import subprocess
import sys
import traceback
from pathlib import Path

import pytest
import structlog
from structlog.testing import capture_logs

from app.config.settings import AppSettings
from app.container import Container
from app.domain.cv.rewrite import RewrittenCV
from app.domain.match.schemas import Eligibility
from app.domain.questions.schemas import GapQuestion, GapQuestions
from app.domain.trust.judge import JudgeFindings
from app.pipeline.checkpoint_types import new_checkpointer
from app.pipeline.errors import PipelineStepFailed
from app.pipeline.graph import build_graph
from app.pipeline.service import PipelineService
from app.pipeline.state import RunOptions
from app.ports.llm_errors import LLMOutputInvalid
from tests.pipeline.helpers import deps_for, persona_profile, tech_jd

ROOT = Path(__file__).resolve().parents[3]


def _service() -> tuple[object, PipelineService]:
    gw, deps = deps_for(
        {
            "jd_extract": [tech_jd()],
            "eligibility": [Eligibility(score=60, gaps=["Kubernetes depth"])],
            "gap_questions": [GapQuestions(questions=[GapQuestion(id="q1", text="K8s?")])],
            "rewrite": [RewrittenCV(), RewrittenCV()],
            "verify_claims": [JudgeFindings()],
        }
    )
    return gw, PipelineService(build_graph(deps, new_checkpointer()), deps.runs)


def _run(svc: PipelineService, tid: str = "t1") -> dict:
    return svc.run(
        job_description="jd text",
        profile={**persona_profile(), "summary": "cv text"},
        thread_id=tid,
        options=RunOptions(),
    )


def test_run_pauses_at_await_answers_then_resume_finishes():
    _, svc = _service()
    _run(svc)
    state = svc.get_state("t1")
    assert state["next"] == ["await_answers"]
    assert state["interrupt"]["type"] == "gap_questions"
    final = svc.resume("t1", "answers")
    assert final["answers"].free_text == "answers"
    assert final["passes"] >= 1
    assert svc.get_state("t1")["next"] == []


def test_calls_get_the_thread_id_and_one_cancel_token_per_invocation():
    gw, svc = _service()
    _run(svc)
    first = len(gw.cancel_tokens)  # type: ignore[attr-defined]
    svc.resume("t1", "answers")
    assert {r.metadata.session_id for r in gw.requests} == {"t1"}  # type: ignore[attr-defined]
    tokens = gw.cancel_tokens  # type: ignore[attr-defined]
    run_tokens, resume_tokens = {id(t) for t in tokens[:first]}, {id(t) for t in tokens[first:]}
    assert len(run_tokens) == 1 and len(resume_tokens) == 1  # svc.cancel reaches every call
    assert run_tokens != resume_tokens


def test_get_state_of_unknown_thread_is_empty():
    _, svc = _service()
    assert svc.get_state("nope") == {"values": {}, "next": [], "interrupt": None}


@pytest.fixture
def stdlib_structlog():
    """structlog's default PrintLogger writes to stdout; route to stdlib logging for this test."""
    structlog.configure(logger_factory=structlog.stdlib.LoggerFactory())
    yield
    structlog.reset_defaults()


def test_no_print_in_pipeline(capsys, stdlib_structlog):
    _, svc = _service()
    _run(svc)
    svc.resume("t1", "answers")
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err == ""


def test_stage_events_carry_no_text():
    _, svc = _service()
    with capture_logs() as logs:
        _run(svc)
        svc.resume("t1", "my private answers")
    stages = [e["stage"] for e in logs if e["event"] == "pipeline.stage"]
    assert stages[:3] == ["jd_extract", "cv_snapshot", "eligibility"]
    blob = json.dumps(logs, default=str)
    for secret in ("jd text", "cv text", "Kubernetes depth", "my private answers"):
        assert secret not in blob


def test_pipeline_parse_failure_does_not_leak():
    secret = "SENTINEL secret cv line"
    _, deps = deps_for({"jd_extract": [LLMOutputInvalid(f"bad reply: {secret}")]})
    svc = PipelineService(build_graph(deps, new_checkpointer()), deps.runs)
    with capture_logs() as logs, pytest.raises(PipelineStepFailed) as exc:
        _run(svc)
    assert exc.value.code == "LLM_OUTPUT_INVALID"
    summary = svc.summary("t1")
    assert summary is not None and summary.error_code == "LLM_OUTPUT_INVALID"
    shown = "".join(traceback.format_exception(exc.value)) + repr(exc.value) + str(exc.value)
    shown += json.dumps(logs, default=str) + summary.model_dump_json()
    assert secret not in shown and "SENTINEL" not in shown


def test_container_builds_pipeline_lazily(monkeypatch):
    import app.container as container_mod

    calls: list[object] = []
    real = container_mod.build_graph

    def spy(deps, checkpointer):
        calls.append(deps)
        return real(deps, checkpointer)

    monkeypatch.setattr(container_mod, "build_graph", spy)
    settings = AppSettings(
        _env_file=None, llm={"default_provider": "fake"}, pipeline={"ats_target": 80}
    )
    c = Container(settings)
    assert calls == []
    first = c.pipeline
    assert isinstance(first, PipelineService)
    assert c.pipeline is first
    assert len(calls) == 1
    assert calls[0].settings.ats_target == 80  # type: ignore[attr-defined]
    assert calls[0].gateway is c.llm  # type: ignore[attr-defined]


def test_graph_and_main_import_without_azure_env(tmp_path):
    strip = re.compile(r"^(AZURE_|SUPABASE_|AUTH__|DB__|REDIS__|SENTRY_DSN$|ENV$)")
    env = {k: v for k, v in os.environ.items() if not strip.match(k)}
    env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", "import app.pipeline.graph, app.main; print('ok')"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ok"
