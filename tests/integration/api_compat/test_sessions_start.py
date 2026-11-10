import re
from types import SimpleNamespace

from core.parsers.input_validator import validate_jd
from services.profile_builder import ProfileBuilder
from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A

JD = (
    "About the role: we are hiring a senior Python engineer to join our team. "
    "Responsibilities include building backend services. Requirements: five years of experience, "
    "strong skills, remote friendly. Benefits and salary are competitive. Candidates should apply. "
) * 3


def _start(client, **body):
    return client.post(
        "/sessions/start", json={"job_description": JD, **body}, headers=auth_header()
    )


def _ready(backend, balance=5):
    backend.store.profiles[USER_A] = {"user_id": USER_A, "full_name": "Test Person"}
    backend.store.balances[USER_A] = balance


def _row(backend, r):
    return backend.store.sessions[r.json()["thread_id"]]


def test_invalid_jd_400_before_profile_check(client):
    r = client.post("/sessions/start", json={"job_description": "too short"}, headers=auth_header())
    assert r.status_code == 400
    assert r.json() == {"detail": validate_jd("too short").user_message}


def test_no_profile_400(client):
    r = _start(client)
    assert r.status_code == 400
    assert r.json() == {"detail": "Please complete your profile first before generating a CV"}


def test_negative_balance_402(client, backend):
    _ready(backend, balance=-1)
    r = _start(client)
    assert r.status_code == 402
    assert r.json() == {"detail": "Not enough coins. You need 0 coins. Current balance: -1"}


def test_start_response_shape(client, backend):
    _ready(backend)
    r = _start(client)
    assert r.status_code == 200
    body = r.json()
    assert re.fullmatch(r"thread_[0-9a-f]{32}", body["thread_id"])
    assert body["status"] == "running"
    assert body["message"] == (
        "CV generation started. Poll /sessions/{thread_id}/status to check progress."
    )


def test_start_creates_session_with_cover_letter_args(client, backend):
    _ready(backend)
    _start(client, cover_letter=True, cover_letter_tone="formal", cover_letter_length="short")
    call = [c for c in backend.store.calls if c[0] == "create_session"][0]
    assert call[2] == {
        "template_id": "classic",
        "domain": None,
        "cover_letter_requested": True,
        "cover_letter_tone": "formal",
        "cover_letter_length": "short",
    }


def test_start_pauses_at_hitl(client, backend):
    _ready(backend)
    backend.pipeline.next_nodes = ["hitl_node"]
    backend.pipeline.values = {
        "gaps_identified": ["g1"],
        "eligibility_verdict": SimpleNamespace(score=55),
    }
    row = _row(backend, _start(client))
    assert row["status"] == "awaiting_hitl"
    assert row["gaps"] == ["g1"]
    assert row["eligibility_score"] == 55


def test_start_pauses_for_cover_letter_options(client, backend):
    _ready(backend)
    backend.pipeline.next_nodes = ["cover_letter_hitl"]
    assert _row(backend, _start(client))["status"] == "awaiting_cover_letter_options"


def test_start_pipeline_error_sets_error(client, backend):
    _ready(backend)
    backend.pipeline.error = RuntimeError("boom")
    r = _start(client)
    assert r.status_code == 200
    assert _row(backend, r)["status"] == "error"


def test_start_passes_profile_text_to_pipeline(client, backend):
    _ready(backend)
    _start(client)
    name, _, kwargs = backend.pipeline.calls[0]
    assert name == "run"
    assert kwargs["user_resume_text"] == ProfileBuilder.from_profile_dict(
        backend.store.profiles[USER_A]
    )
