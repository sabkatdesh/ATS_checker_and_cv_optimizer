import re
from types import SimpleNamespace

from app.domain.parsing.input_validator import validate_jd
from app.domain.questions.schemas import GapQuestion
from app.pipeline.state import RunOptions
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


COMPLETE = {
    "user_id": USER_A,
    "full_name": "Test Person",
    "email": "test@example.com",
    "education": [{"degree": "BSc", "institution": "Example University"}],
}


def _ready(backend, balance=5, profile=None):
    backend.store.profiles[USER_A] = profile or dict(COMPLETE)
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
    backend.pipeline.next_nodes = ["await_answers"]
    backend.pipeline.values = {
        "questions": [GapQuestion(id="q1", text="g1")],
        "eligibility": SimpleNamespace(score=55),
    }
    row = _row(backend, _start(client))
    assert row["status"] == "awaiting_hitl"
    assert row["gaps"] == ["g1"]
    assert row["eligibility_score"] == 55


def test_start_pauses_for_cover_letter_options(client, backend):
    _ready(backend)
    backend.pipeline.next_nodes = ["cover_letter_options"]
    assert _row(backend, _start(client))["status"] == "awaiting_cover_letter_options"


def test_start_pipeline_error_sets_error(client, backend):
    _ready(backend)
    backend.pipeline.error = RuntimeError("boom")
    r = _start(client)
    assert r.status_code == 200
    assert _row(backend, r)["status"] == "error"


def test_start_passes_the_profile_dict_to_pipeline(client, backend):
    _ready(backend)
    _start(client)
    name, _, kwargs = backend.pipeline.calls[0]
    assert name == "run"
    assert kwargs["profile"] == backend.store.profiles[USER_A]
    assert "user_resume_text" not in kwargs


def test_incomplete_profile_is_422_before_session_or_coins(client, backend):
    _ready(backend, profile={"user_id": USER_A, "full_name": "Test Person"})
    r = _start(client)
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "PROFILE_INCOMPLETE"
    assert body["missing"] == ["CONTACT", "EXPERIENCE_OR_EDUCATION"]
    assert "Test Person" not in r.text
    assert backend.store.sessions == {}
    assert not [c for c in backend.store.calls if c[0] in ("create_session", "deduct_coins")]
    assert backend.store.balances[USER_A] == 5
    assert backend.pipeline.calls == []


def test_incomplete_profile_is_422_even_with_no_coins(client, backend):
    _ready(backend, balance=-1, profile={"user_id": USER_A, "email": "test@example.com"})
    r = _start(client)
    assert r.status_code == 422
    assert r.json()["missing"] == ["NAME", "EXPERIENCE_OR_EDUCATION"]


def test_start_builds_run_options(client, backend):
    _ready(backend)
    _start(client, cover_letter=True, cover_letter_tone="casual", cover_letter_length="short")
    options = backend.pipeline.calls[0][2]["options"]
    assert options == RunOptions(
        cover_letter=True, cover_letter_tone=None, cover_letter_length="short", max_passes=2
    )
