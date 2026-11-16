"""BedrockConverseTransport: lazy client, thread hand-off, stream path, error mapping."""

import asyncio
from typing import Any

import pytest
from botocore.exceptions import NoCredentialsError

from app.adapters.llm import bedrock_converse as bc
from app.adapters.llm.registry import DEFAULT_FACTORIES
from app.config.settings import AppSettings
from app.ports.llm import CancelToken, Usage
from app.ports.llm_errors import LLMAuthError
from tests.unit.llm.test_bedrock_wire import MODEL, response, wire


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def converse(self, **kw: Any) -> dict:
        self.calls.append(("converse", kw))
        return response()

    def converse_stream(self, **kw: Any) -> dict:
        self.calls.append(("converse_stream", kw))
        events = [
            {"contentBlockDelta": {"delta": {"text": "streamed"}, "contentBlockIndex": 0}},
            {"messageStop": {"stopReason": "end_turn"}},
            {"metadata": {"usage": {"inputTokens": 5, "outputTokens": 1, "totalTokens": 6}}},
        ]
        return {"stream": iter(events)}


class FakeSession:
    made: list[dict] = []

    def client(self, service: str, **kw: Any) -> FakeClient:
        FakeSession.made.append({"service": service, **kw})
        return FakeClient()


def test_client_is_built_lazily_once_with_single_attempt_retries(monkeypatch):
    FakeSession.made = []
    monkeypatch.setattr(bc.boto3.session, "Session", FakeSession)
    t = bc.BedrockConverseTransport(region="us-east-1", read_timeout_s=160)
    assert FakeSession.made == []
    for _ in range(2):
        asyncio.run(t.send(wire(), CancelToken()))
    assert len(FakeSession.made) == 1
    made = FakeSession.made[0]
    assert made["service"] == "bedrock-runtime" and made["region_name"] == "us-east-1"
    cfg = made["config"]
    assert cfg.retries == {"mode": "adaptive", "total_max_attempts": 1}
    assert cfg.read_timeout == 160 and cfg.connect_timeout == 5


def test_non_stream_uses_converse():
    client = FakeClient()
    t = bc.BedrockConverseTransport(region="r", read_timeout_s=10, client=client)
    raw = asyncio.run(t.send(wire(), CancelToken()))
    assert raw.text == "hi" and client.calls[0][0] == "converse"
    assert client.calls[0][1]["modelId"] == MODEL


def test_stream_uses_converse_stream_and_accumulates():
    client = FakeClient()
    t = bc.BedrockConverseTransport(region="r", read_timeout_s=10, client=client)
    raw = asyncio.run(t.send(wire(stream=True), CancelToken()))
    assert client.calls[0][0] == "converse_stream"
    assert raw.text == "streamed" and raw.stop == "end"
    assert raw.usage == Usage(input_tokens=5, output_tokens=1)


def test_missing_credentials_surface_as_auth_error_on_first_call():
    class NoCreds(FakeClient):
        def converse(self, **kw: Any) -> dict:
            raise NoCredentialsError()

    t = bc.BedrockConverseTransport(region="r", read_timeout_s=10, client=NoCreds())
    with pytest.raises(LLMAuthError) as exc:
        asyncio.run(t.send(wire(), CancelToken()))
    assert exc.value.detail == "NoCredentialsError"


def test_factory_is_registered_and_does_no_aws_work(monkeypatch):
    def boom(*_a: Any, **_k: Any) -> None:
        raise AssertionError("factory must not build a boto3 session")

    monkeypatch.setattr(bc.boto3.session, "Session", boom)
    settings = AppSettings(_env_file=None)  # type: ignore[call-arg]
    t = DEFAULT_FACTORIES["bedrock"](settings)
    assert t.name == "bedrock" and t.supports_native_schema is True
    assert isinstance(t, bc.BedrockConverseTransport)


def test_smoke_dry_run_prints_cost_and_makes_no_call(monkeypatch, capsys):
    from app.adapters.llm import _smoke

    monkeypatch.setattr(_smoke, "load_settings", lambda: AppSettings(_env_file=None))

    def no_registry(*_a: Any, **_k: Any) -> None:
        raise AssertionError("dry run must not build providers")

    monkeypatch.setattr(_smoke, "ProviderRegistry", no_registry)
    assert _smoke.main([]) == 0
    out = capsys.readouterr().out
    assert "estimated cost" in out and "max_tokens=1500" in out and "no call made" in out
    assert "fallback: disabled" in out
