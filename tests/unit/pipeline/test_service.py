import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import structlog
from langgraph.checkpoint.memory import MemorySaver
from structlog.testing import capture_logs

from app.config.settings import AppSettings
from app.container import Container
from app.domain.match.schemas import SummaryCV
from app.domain.parsing.safe_parser import safe_llm_parse
from app.pipeline.chains import build_chains
from app.pipeline.graph import build_graph
from app.pipeline.service import PipelineService
from tests.fakes.fake_chat_model import RoutingFakeChatModel

ROOT = Path(__file__).resolve().parents[3]

_VERDICT = {
    "score": 60,
    "verdict": "Partially Align 60%",
    "reason": ["ok"],
    "gaps_to_consider": ["Kubernetes depth"],
}


def _fake() -> RoutingFakeChatModel:
    return RoutingFakeChatModel(
        routes=[
            ("Assess whether this candidate", json.dumps(_VERDICT)),
            ("EVIDENCE-ONLY RULE", "{}"),
        ],
        default="{}",
    )


def _service(llm=None) -> PipelineService:
    graph = build_graph(build_chains(llm or _fake()), MemorySaver())
    return PipelineService(graph)


def _run(svc: PipelineService, tid: str = "t1") -> dict:
    return svc.run(
        job_description="jd text",
        user_resume_text="cv text",
        thread_id=tid,
        cover_letter_requested=False,
    )


def test_run_pauses_at_hitl_then_resume_finishes():
    svc = _service()
    _run(svc)
    state = svc.get_state("t1")
    assert state["next"] == ["hitl_node"]
    assert state["is_paused_at_hitl"] is True
    final = svc.resume("t1", "answers")
    assert final["user_qna"] == "answers"
    assert final["counter"] >= 1
    assert svc.get_state("t1")["next"] == []


@pytest.fixture
def stdlib_structlog():
    """structlog's default PrintLogger writes to stdout; route to stdlib logging for this test."""
    structlog.configure(logger_factory=structlog.stdlib.LoggerFactory())
    yield
    structlog.reset_defaults()


def test_no_print_in_pipeline(capsys, stdlib_structlog):
    svc = _service()
    _run(svc)
    svc.resume("t1", "answers")
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err == ""


def test_stage_events_carry_no_text():
    svc = _service()
    with capture_logs() as logs:
        _run(svc)
        svc.resume("t1", "my private answers")
    assert any(entry["event"] == "pipeline.stage" for entry in logs)
    blob = json.dumps(logs, default=str)
    for secret in ("jd text", "cv text", "Kubernetes depth", "my private answers"):
        assert secret not in blob


def test_parse_fail_log_has_no_raw_text():
    garbage = "secret cv line nothing parseable here"
    with capture_logs() as logs:
        safe_llm_parse(garbage, SummaryCV, SummaryCV())
    assert logs
    assert any(entry["event"] == "llm.parse_failed" for entry in logs)
    assert "secret cv line" not in json.dumps(logs, default=str)


def test_pipeline_parse_failure_does_not_leak(capsys):
    llm = RoutingFakeChatModel(default="secret cv line garbage")
    svc = _service(llm)
    with capture_logs() as logs:
        _run(svc)
    captured = capsys.readouterr()
    assert "secret cv line" not in captured.out + captured.err
    assert "secret cv line" not in json.dumps(logs, default=str)


def test_container_builds_pipeline_lazily(monkeypatch):
    import app.container as container_mod

    calls: list[int] = []
    fake = _fake()

    class _Client:
        llm = fake

    def fake_build(settings):
        calls.append(1)
        return _Client()

    monkeypatch.setattr(container_mod, "build_azure_client", fake_build)
    c = Container(AppSettings(_env_file=None))
    assert calls == []
    first = c.pipeline
    assert isinstance(first, PipelineService)
    assert c.pipeline is first
    assert calls == [1]


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
