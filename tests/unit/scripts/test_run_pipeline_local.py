import json
import socket

import pytest

from scripts.run_pipeline_local import main

PERSONAS = (
    "tech_backend",
    "nurse_icu",
    "electrician_trades",
    "teacher_volunteer",
    "banker_mixed_bn",
    "fresh_graduate_sparse",
)
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    real_connect = socket.socket.connect

    def guarded(self: socket.socket, address: object) -> None:
        if isinstance(address, tuple) and address and address[0] in _LOOPBACK:
            return real_connect(self, address)  # type: ignore[arg-type]
        raise AssertionError("the local run must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", guarded)


def test_nurse_fixture_runs_offline_and_prints_the_trust_report(capsys):
    assert main(["--fixture", "nurse_icu"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["fixture"] == "nurse_icu"
    assert out["summary"]["trust_report"]["status"] == "pass"
    assert out["steps"] == [
        "jd_extract",
        "eligibility",
        "gap_questions",
        "rewrite",
        "verify_claims",
    ]


@pytest.mark.parametrize("name", PERSONAS)
def test_every_persona_runs_with_a_cover_letter(name: str, capsys):
    assert main(["--fixture", name, "--cover-letter"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["summary"]["trust_report"]["status"] == "pass"
    assert out["steps"][-1] == "cover_letter"


def test_unknown_fixture_exits_2(capsys):
    assert main(["--fixture", "no_such_persona"]) == 2
    assert "no_such_persona" in capsys.readouterr().err
