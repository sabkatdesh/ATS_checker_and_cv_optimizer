"""Terminal sessions keep their final summary in cv_sessions and drop the thread's checkpoints."""

from types import SimpleNamespace

import pytest
from structlog.testing import capture_logs

from app.adapters.background.inline_runner import InlineRunner
from app.config.settings import AppSettings
from app.container import Container
from app.pipeline.errors import PipelineCancelled, PipelineStepFailed
from app.pipeline.summary import SessionSummary
from app.services.finalize import finalize_session
from app.services.generation import resume_after_answers, run_new_session
from tests.fakes.backend import FakeBackend, backend_with_session
from tests.fakes.fake_auth import USER_A
from tests.fakes.fake_renderers import FakeCoverLetterRenderer, FakePdfRenderer

TID = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a06"
SUMMARY = SessionSummary(domain="tech", eligibility_score=70, ats_after=88)


class _Factory:
    """Records delete_thread calls in the shared event log."""

    def __init__(self, log: list, error: Exception | None = None) -> None:
        self.log, self.error = log, error

    def open_async(self):  # pragma: no cover - not used by the services
        raise AssertionError

    def reader(self):  # pragma: no cover
        raise AssertionError

    def delete_thread(self, thread_id: str) -> None:
        self.log.append(("delete", thread_id))
        if self.error is not None:
            raise self.error


def _container(log: list, error: Exception | None = None) -> tuple[Container, FakeBackend]:
    backend = backend_with_session(USER_A, TID)
    real_update = backend.sessions.update

    def update(user_id, session_id, **fields):
        log.append(("update", fields.get("status"), fields.get("pipeline_summary")))
        real_update(user_id, session_id, **fields)

    backend.sessions.update = update  # type: ignore[method-assign]
    backend.pipeline.summary_value = SUMMARY
    c = Container(
        AppSettings(_env_file=None, env="test"),
        **backend.repos(),
        pipeline=backend.pipeline,
        checkpointer=_Factory(log, error),
        runner=InlineRunner(),
        pdf_factory=FakePdfRenderer,
        cover_letter_factory=FakeCoverLetterRenderer,
    )
    return c, backend


def _result() -> dict:
    return {
        "eligible": True,
        "eligibility": SimpleNamespace(score=70),
        "tailored_cv": {"full_name": "T"},
        "domain": "tech",
    }


def _start(c: Container) -> None:
    run_new_session(
        c,
        user_id=USER_A,
        thread_id=TID,
        profile={},
        job_description="jd",
        cover_letter=False,
        cover_letter_tone=None,
        cover_letter_length=None,
    )


def test_terminal_session_copies_summary_then_deletes_thread():
    log: list = []
    c, backend = _container(log)
    finalize_session(c, TID, _result(), USER_A, {})
    stored = SUMMARY.model_dump(mode="json")
    assert log == [("update", "succeeded", stored), ("delete", TID)]
    row = backend.sessions.get(USER_A, TID)
    assert row is not None and row.pipeline_summary == stored


def test_ineligible_session_copies_summary_then_deletes_thread():
    log: list = []
    c, _ = _container(log)
    finalize_session(c, TID, {"eligible": False, "domain": "tech"}, USER_A, {})
    assert log == [("update", "ineligible", SUMMARY.model_dump(mode="json")), ("delete", TID)]


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (PipelineStepFailed("rewrite", "LLM_OUTPUT_INVALID"), "failed"),
        (PipelineCancelled("rewrite", "rewrite", "before"), "cancelled"),
        (RuntimeError("boom"), "failed"),
    ],
)
def test_failed_and_cancelled_sessions_archive_then_delete(error, status):
    log: list = []
    c, backend = _container(log)
    backend.pipeline.error = error
    _start(c)
    assert log == [("update", status, SUMMARY.model_dump(mode="json")), ("delete", TID)]


def test_paused_session_keeps_its_checkpoints():
    log: list = []
    c, backend = _container(log)
    backend.pipeline.next_nodes = ["await_answers"]
    _start(c)
    assert [e[0] for e in log] == ["update"]
    assert log[0][1] == "awaiting_input"


def test_delete_failure_is_logged_not_raised():
    log: list = []
    c, backend = _container(log, error=RuntimeError("db down: secret-dsn"))
    with capture_logs() as logs:
        finalize_session(c, TID, _result(), USER_A, {})
    row = backend.sessions.get(USER_A, TID)
    assert row is not None and row.status == "succeeded"
    events = [e for e in logs if e["event"] == "pipeline.checkpoint_delete_failed"]
    assert len(events) == 1
    assert "secret-dsn" not in repr(logs)


def test_summary_failure_keeps_checkpoints_for_the_sweep():
    log: list = []
    c, backend = _container(log)
    backend.pipeline.summary_error = RuntimeError("reader down")
    backend.pipeline.result = _result()
    resume_after_answers(c, user_id=USER_A, thread_id=TID, reply="x")
    assert log == [("update", "succeeded", None)]
