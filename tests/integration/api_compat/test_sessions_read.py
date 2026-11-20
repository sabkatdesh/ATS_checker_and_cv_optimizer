from datetime import UTC, datetime

import pytest

from app.domain.cv.domain_config import Domain
from app.domain.jd.meta import JdMeta
from app.pipeline.summary import SessionSummary
from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A, USER_B

CREATED = datetime(2026, 11, 20, 9, 30, tzinfo=UTC)
NOT_FOUND = (404, {"detail": "Session not found"})


def _status(client, sid):
    return client.get(f"/sessions/{sid}/status", headers=auth_header())


def test_status_404(client):
    r = _status(client, "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b")
    assert (r.status_code, r.json()) == NOT_FOUND


@pytest.mark.parametrize("bad", ["nope", "thread_abc123", "1", "0190a1b2c3d47e5f8a9b0c1d2e3f4a5b"])
def test_malformed_session_id_404(client, backend, bad):
    r = _status(client, bad)
    assert (r.status_code, r.json()) == NOT_FOUND
    for path, body in (("reply", {"skipped": True}), ("cover-letter", {"text": "x"})):
        r = client.post(f"/sessions/{bad}/{path}", json=body, headers=auth_header())
        assert (r.status_code, r.json()) == NOT_FOUND


def test_get_other_users_session_is_none_and_api_404(client, backend):
    sid = backend.sessions.seed(USER_B, status="succeeded", jd_text="secret jd")
    assert backend.sessions.get(USER_A, sid) is None
    r = _status(client, sid)
    assert (r.status_code, r.json()) == NOT_FOUND
    assert "secret" not in r.text


def test_status_maps_the_row_to_the_legacy_shape(client, backend):
    sid = backend.sessions.seed(
        USER_A,
        status="succeeded",
        jd_text="jd",
        jd_domain="tech",
        template_id="classic",
        score_after=80,
        score_breakdown={"eligibility_score": 70},
        options={"cover_letter": True, "cover_letter_tone": "formal"},
        cover_letter_text="Dear",
        created_at=CREATED,
    )
    r = _status(client, sid)
    assert r.status_code == 200
    assert r.json() == {
        "thread_id": sid,
        "user_id": USER_A,
        "status": "complete",
        "job_description": "jd",
        "ats_score": 80,
        "semantic_score": None,
        "improvement_score": None,
        "eligibility_score": 70,
        "gaps": [],
        "pdf_url": None,
        "template_id": "classic",
        "domain": "tech",
        "cover_letter_requested": True,
        "cover_letter_tone": "formal",
        "cover_letter_length": None,
        "cover_letter_text": "Dear",
        "cover_letter_pdf_url": None,
        "created_at": CREATED.isoformat(),
        "pipeline": None,
    }


@pytest.mark.parametrize(
    ("status", "kind", "legacy"),
    [
        ("running", None, "running"),
        ("awaiting_input", "questions", "awaiting_hitl"),
        ("awaiting_input", "cover_letter_options", "awaiting_cover_letter_options"),
        ("failed", None, "error"),
        ("ineligible", None, "ineligible"),
    ],
)
def test_status_strings_stay_legacy(client, backend, status, kind, legacy):
    sid = backend.sessions.seed(USER_A, status=status, awaiting_kind=kind)
    assert _status(client, sid).json()["status"] == legacy


def test_status_adds_pipeline_summary(client, backend):
    sid = backend.sessions.seed(USER_A)
    backend.pipeline.summary_value = SessionSummary(
        jd=JdMeta(title="Staff Nurse", company="Example", domain=Domain.MEDICAL),
        domain="medical",
        eligibility_score=60,
    )
    r = _status(client, sid)
    assert r.json()["pipeline"] == {
        "jd": {
            "title": "Staff Nurse",
            "company": "Example",
            "domain": "medical",
            "location": None,
            "deadline": None,
            "application_email": None,
        },
        "domain": "medical",
        "eligibility_score": 60,
        "ats_before": None,
        "ats_after": None,
        "trust_report": None,
        "warnings": [],
        "error_code": None,
        "cancelled_stage": None,
    }
    assert ("summary", (sid,), {}) in backend.pipeline.calls


def test_status_falls_back_to_the_stored_summary(client, backend):
    sid = backend.sessions.seed(USER_A, pipeline_summary={"domain": "tech"})
    assert _status(client, sid).json()["pipeline"] == {"domain": "tech"}


def test_finished_session_uses_the_stored_summary(client, backend):
    """Checkpoints of a finished session are gone; the live summary would be partial."""
    sid = backend.sessions.seed(USER_A, status="failed", pipeline_summary={"domain": "tech"})
    backend.pipeline.summary_value = SessionSummary(error_code="LLM_OUTPUT_INVALID")
    assert _status(client, sid).json()["pipeline"] == {"domain": "tech"}
    assert ("summary", (sid,), {}) not in backend.pipeline.calls


def test_status_survives_a_failing_summary(client, backend):
    from structlog.testing import capture_logs

    sid = backend.sessions.seed(USER_A)
    backend.pipeline.summary_error = RuntimeError("SENTINEL secret cv text")
    with capture_logs() as logs:
        r = _status(client, sid)
    assert r.status_code == 200
    assert r.json()["pipeline"] is None
    assert r.json()["status"] == "running"
    failed = [e for e in logs if e["event"] == "pipeline.summary_failed"]
    assert len(failed) == 1 and "SENTINEL" not in str(logs)


LIST_FIELDS = {
    "thread_id",
    "status",
    "job_description",
    "ats_score",
    "semantic_score",
    "improvement_score",
    "eligibility_score",
    "pdf_url",
    "template_id",
    "domain",
    "cover_letter_requested",
    "cover_letter_text",
    "cover_letter_pdf_url",
    "created_at",
}


def test_list_sessions(client, backend):
    older = backend.sessions.seed(USER_A)
    newer = backend.sessions.seed(USER_A, status="succeeded")
    backend.sessions.seed(USER_B)
    r = client.get("/sessions", headers=auth_header())
    assert r.status_code == 200
    sessions = r.json()["sessions"]
    assert [s["thread_id"] for s in sessions] == [newer, older]
    assert all(set(s) == LIST_FIELDS for s in sessions)
    assert sessions[0]["status"] == "complete"
