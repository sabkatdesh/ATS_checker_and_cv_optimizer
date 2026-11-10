import logging

from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A
from tests.fakes.fake_renderers import FakePdfRenderer
from tests.integration.api_compat.conftest import backend, client  # noqa: F401

JD = (
    "About the role: we are hiring a senior Python engineer to join our team. "
    "Responsibilities include building backend services. Requirements: five years of experience, "
    "strong skills, remote friendly. Benefits and salary are competitive. Candidates should apply. "
) * 3


def test_pdf_failure_logs_traceback_and_session_completes(client, backend, caplog):  # noqa: F811
    from types import SimpleNamespace

    FakePdfRenderer.raise_on_render = RuntimeError("render failed")
    backend.store.profiles[USER_A] = {"user_id": USER_A, "full_name": "Test Person"}
    backend.pipeline.next_nodes = []
    backend.pipeline.result = {
        "is_eligible": True,
        "final_match": {"overall_score": 82},
        "eligibility_verdict": SimpleNamespace(score=70),
        "structured_cv": {"full_name": "Test Person"},
    }
    with caplog.at_level(logging.ERROR):
        r = client.post("/sessions/start", json={"job_description": JD}, headers=auth_header())
    row = backend.store.sessions[r.json()["thread_id"]]
    assert row["status"] == "complete"
    assert row["pdf_url"] is None
    assert any(rec.exc_info for rec in caplog.records if rec.levelno >= logging.ERROR)
