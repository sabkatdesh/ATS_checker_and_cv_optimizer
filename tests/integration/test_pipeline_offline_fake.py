"""The legacy pipeline end to end on the real container, router and fake provider: no network."""

import socket
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.adapters.background.inline_runner import InlineRunner
from app.config.settings import AppSettings
from app.container import LEGACY_CHAIN_ROUTES, Container
from app.domain.cv.rewrite import RewrittenCV
from app.main import create_app
from tests.fakes.backend import auth_header
from tests.fakes.fake_auth import USER_A, FakeAuth
from tests.fakes.fake_renderers import FakeCoverLetterRenderer, FakePdfRenderer
from tests.fakes.memory_store import MemoryStore

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
JD = (
    "About the role: we are hiring a senior Python engineer to join our team. "
    "Responsibilities include building backend services. Requirements: five years of experience, "
    "strong skills, remote friendly. Benefits and salary are competitive. Candidates should apply. "
) * 3


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    real_connect = socket.socket.connect

    def guarded(self: socket.socket, address: object) -> None:
        # asyncio's self-pipe on Windows is a loopback socketpair; anything else is a leak.
        if isinstance(address, tuple) and address and address[0] in _LOOPBACK:
            return real_connect(self, address)  # type: ignore[arg-type]
        raise AssertionError("offline pipeline tests must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", guarded)


@pytest.fixture
def container() -> Container:
    FakePdfRenderer.calls.clear()
    FakePdfRenderer.raise_on_render = None
    FakeCoverLetterRenderer.calls.clear()
    FakeCoverLetterRenderer.raise_on_render = None
    return Container(
        AppSettings(_env_file=None, env="test", llm={"default_provider": "fake"}),
        store=MemoryStore(),
        auth=FakeAuth(),
        runner=InlineRunner(),
        pdf_factory=FakePdfRenderer,
        cover_letter_factory=FakeCoverLetterRenderer,
    )


def _run(c: Container, tid: str = "t1", **kw: object) -> None:
    c.pipeline.run(
        job_description=JD, user_resume_text="Jane Doe, Python engineer.", thread_id=tid, **kw
    )  # type: ignore[arg-type]


def test_full_pipeline_runs_offline_on_fake_provider(container):
    _run(container)
    state = container.pipeline.get_state("t1")
    assert state["next"] == ["hitl_node"]
    final = container.pipeline.resume("t1", "I have used Kubernetes for two years.")
    # The legacy graph stores the rewrite in structured_cv (re_write_cv is never written).
    assert isinstance(final["structured_cv"], RewrittenCV)
    assert final["counter"] >= 1
    assert final["final_match"] is not None
    assert container.pipeline.get_state("t1")["next"] == []


def test_cover_letter_path_offline(container):
    _run(
        container,
        cover_letter_requested=True,
        cover_letter_tone="formal",
        cover_letter_length="short",
    )
    final = container.pipeline.resume("t1", "answers")
    assert final["cover_letter_result"] is not None
    assert final["cover_letter_result"].opening_paragraph != (
        "I am excited to apply for this position."
    )


def test_usage_records_cover_every_legacy_prompt(container):
    _run(
        container,
        cover_letter_requested=True,
        cover_letter_tone="formal",
        cover_letter_length="short",
    )
    container.pipeline.resume("t1", "answers")
    container.make_llm_client().invoke_structured("x" * 120, _profile_schema())
    recs = container.usage_sink.records()  # type: ignore[attr-defined]
    expected = {f"legacy.{chain}" for chain in LEGACY_CHAIN_ROUTES} | {"legacy.profile_import"}
    assert {r.prompt_id for r in recs} == expected
    assert all(r.provider == "fake" and r.status == "ok" for r in recs)
    assert all(r.cost_usd == Decimal(0) for r in recs)
    steps = {r.prompt_id: r.step for r in recs}
    assert all(steps[f"legacy.{c}"] == s for c, s in LEGACY_CHAIN_ROUTES.items())


def _profile_schema():
    from app.domain.cv.universal_cv import UniversalCVStructured

    return UniversalCVStructured


def test_api_start_and_reply_offline(container):
    container.store.profiles[USER_A] = {"user_id": USER_A, "full_name": "Jane Doe"}
    container.store.balances[USER_A] = 5
    client = TestClient(create_app(container), raise_server_exceptions=False)
    r = client.post("/sessions/start", json={"job_description": JD}, headers=auth_header())
    assert r.status_code == 200
    tid = r.json()["thread_id"]
    status = client.get(f"/sessions/{tid}/status", headers=auth_header()).json()
    assert status["status"] == "awaiting_hitl"
    r = client.post(f"/sessions/{tid}/reply", json={"user_qna": "answers"}, headers=auth_header())
    assert r.status_code == 200
    r = client.get(f"/sessions/{tid}/status", headers=auth_header())
    assert r.status_code == 200
    assert r.json()["status"] == "complete"
    assert r.json()["pdf_url"]
    values = container.pipeline.get_state(tid)["values"]
    assert isinstance(values["structured_cv"], RewrittenCV) and values["counter"] >= 1
    assert FakePdfRenderer.calls


def test_profile_import_offline(container):
    client = TestClient(create_app(container), raise_server_exceptions=False)
    r = client.post("/profile/import-cv", json={"cv_text": "x" * 150}, headers=auth_header())
    assert r.status_code == 200
    assert r.json()["profile"]["meta"]["full_name"] == "Jane Example"
