from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A, USER_B


def _reply(client):
    return client.post("/sessions/t1/reply", json={"user_qna": "answers"}, headers=auth_header())


def _session(backend, status="awaiting_hitl", user=USER_A):
    backend.store.sessions["t1"] = {"thread_id": "t1", "user_id": user, "status": status}


def test_reply_404_403(client, backend):
    r = _reply(client)
    assert (r.status_code, r.json()) == (404, {"detail": "Session not found"})
    _session(backend, user=USER_B)
    r = _reply(client)
    assert (r.status_code, r.json()) == (403, {"detail": "Not your session"})


def test_reply_wrong_status_400(client, backend):
    _session(backend, status="running")
    r = _reply(client)
    assert r.status_code == 400
    assert r.json() == {"detail": "Session is not waiting for your input"}


def test_reply_ok_response(client, backend):
    _session(backend)
    r = _reply(client)
    assert r.status_code == 200
    assert r.json() == {"status": "resumed", "message": "Pipeline resumed. Keep polling /status"}
    assert ("resume", ("t1", "answers"), {}) in backend.pipeline.calls


def test_reply_then_cover_letter_options(client, backend):
    _session(backend)
    backend.pipeline.next_nodes = ["cover_letter_hitl"]
    _reply(client)
    assert backend.store.sessions["t1"]["status"] == "awaiting_cover_letter_options"


def test_reply_then_finalize(client, backend):
    _session(backend)
    backend.pipeline.result = {"is_eligible": True}
    _reply(client)
    assert backend.store.sessions["t1"]["status"] == "complete"


def test_reply_error(client, backend):
    _session(backend)
    backend.pipeline.error = RuntimeError("boom")
    r = _reply(client)
    assert r.status_code == 200
    assert backend.store.sessions["t1"]["status"] == "error"
