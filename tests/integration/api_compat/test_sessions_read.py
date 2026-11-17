from app.pipeline.summary import JdMeta, SessionSummary
from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A, USER_B


def test_status_404(client):
    r = client.get("/sessions/nope/status", headers=auth_header())
    assert r.status_code == 404
    assert r.json() == {"detail": "Session not found"}


def test_status_403(client, backend):
    backend.store.sessions["t1"] = {"thread_id": "t1", "user_id": USER_B}
    r = client.get("/sessions/t1/status", headers=auth_header())
    assert r.status_code == 403
    assert r.json() == {"detail": "Not your session"}


def test_status_returns_row_verbatim(client, backend):
    row = {
        "thread_id": "t1",
        "user_id": USER_A,
        "status": "complete",
        "ats_score": 80,
        "extra": [1],
    }
    backend.store.sessions["t1"] = row
    r = client.get("/sessions/t1/status", headers=auth_header())
    assert r.status_code == 200
    assert r.json() == {**row, "pipeline": None}


def test_status_adds_pipeline_summary(client, backend):
    backend.store.sessions["t1"] = {"thread_id": "t1", "user_id": USER_A, "status": "running"}
    backend.pipeline.summary_value = SessionSummary(
        jd=JdMeta(job_title="Nurse", company_name="Example", domain="medical"),
        domain="medical",
        eligibility_score=60,
    )
    r = client.get("/sessions/t1/status", headers=auth_header())
    assert r.json()["pipeline"] == {
        "jd": {"job_title": "Nurse", "company_name": "Example", "domain": "medical"},
        "domain": "medical",
        "eligibility_score": 60,
        "ats_before": None,
        "ats_after": None,
        "trust_report": None,
        "warnings": [],
        "error_code": None,
    }
    assert ("summary", ("t1",), {}) in backend.pipeline.calls


def test_status_survives_a_failing_summary(client, backend):
    from structlog.testing import capture_logs

    row = {"thread_id": "t1", "user_id": USER_A, "status": "running"}
    backend.store.sessions["t1"] = row
    backend.pipeline.summary_error = RuntimeError("SENTINEL secret cv text")
    with capture_logs() as logs:
        r = client.get("/sessions/t1/status", headers=auth_header())
    assert r.status_code == 200
    assert r.json() == {**row, "pipeline": None}
    failed = [e for e in logs if e["event"] == "pipeline.summary_failed"]
    assert len(failed) == 1 and "SENTINEL" not in str(logs)


def test_list_sessions(client, backend):
    backend.store.sessions["t1"] = {"thread_id": "t1", "user_id": USER_A}
    backend.store.sessions["t2"] = {"thread_id": "t2", "user_id": USER_B}
    r = client.get("/sessions", headers=auth_header())
    assert r.status_code == 200
    assert r.json() == {"sessions": backend.store.get_user_sessions(USER_A)}
    assert [s["thread_id"] for s in r.json()["sessions"]] == ["t1"]
