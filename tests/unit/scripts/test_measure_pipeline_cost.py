import re
import socket
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.llm._breaker import BreakerRegistry
from app.adapters.llm._pricing import PriceTable
from app.adapters.llm.fake import FakeTransport
from app.adapters.llm.registry import ProviderRegistry
from app.adapters.llm.router import LLMRouter
from app.adapters.llm.usage_recorder import UsageRecorder
from app.adapters.usage.memory_sink import MemoryUsageSink
from app.config.llm_routes import load_route_table
from app.config.settings import AppSettings
from scripts._cost_gate import BudgetedGateway
from scripts.measure_pipeline_cost import main, run_persona

PERSONAS = Path(__file__).resolve().parents[2] / "fixtures" / "personas"
SETTINGS = AppSettings(_env_file=None, env="test")


_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    real_connect = socket.socket.connect

    def guarded(self: socket.socket, address: object) -> None:
        if isinstance(address, tuple) and address and address[0] in _LOOPBACK:
            return real_connect(self, address)  # type: ignore[arg-type]
        raise AssertionError("the cost script tests must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", guarded)


def test_dry_run_offline(capsys):
    assert main(["--dry-run"], settings=SETTINGS) == 0
    out = capsys.readouterr().out
    match = re.search(r"worst case per call \(max\) \$([0-9.]+) <= cap \$([0-9.]+)", out)
    assert match is not None
    assert Decimal(match.group(1)) <= Decimal(match.group(2))
    assert "estimate" in out
    assert "no network call made" in out


def test_dry_run_is_the_default(capsys):
    assert main([], settings=SETTINGS) == 0
    assert "no network call made" in capsys.readouterr().out


def test_paid_requires_yes(capsys):
    assert main(["--no-dry-run"], settings=SETTINGS) == 2
    assert "--yes" in capsys.readouterr().err


def test_yes_alone_is_not_paid(capsys):
    assert main(["--yes"], settings=SETTINGS) == 2
    assert "--no-dry-run" in capsys.readouterr().err


def test_non_finite_cap_refused(capsys):
    for bad in ("NaN", "Infinity", "abc"):
        assert main(["--cap", bad], settings=SETTINGS) == 2
    assert "cap" in capsys.readouterr().err


def test_cap_defaults_to_0_50(capsys):
    main(["--dry-run"], settings=SETTINGS)
    assert "cap $0.50" in capsys.readouterr().out


def test_cap_above_0_50_refused(capsys):
    assert main(["--dry-run", "--cap", "0.51"], settings=SETTINGS) == 2
    assert "0.50" in capsys.readouterr().err


def test_unknown_persona_refused(capsys):
    assert main(["--personas", "nobody"], settings=SETTINGS) == 2
    assert "nobody" in capsys.readouterr().err


def test_run_persona_measures_a_full_run_on_the_fake_provider():
    settings = AppSettings(_env_file=None, env="test", llm={"default_provider": "fake"})
    prices = PriceTable.from_file(settings.llm.prices_file)
    sink = MemoryUsageSink()
    transport = FakeTransport(defaults_dir=PERSONAS / "nurse_icu" / "replies")
    registry = ProviderRegistry(
        settings,
        prices=prices,
        breakers=BreakerRegistry(),
        factories={"fake": lambda _s: transport},
    )
    router = LLMRouter(
        load_route_table(settings.llm, prices), registry, UsageRecorder(sink, prices)
    )
    gate = BudgetedGateway(router, Decimal("0.50"), lambda _r: Decimal("0"))
    run = run_persona("nurse_icu", gate, sink, settings.pipeline)
    assert run.persona == "nurse_icu"
    assert run.calls == len(sink.records()) >= 6
    assert run.verifier_status == "pass"
    assert {s.step for s in run.steps} >= {"jd_extract", "rewrite", "cover_letter"}
