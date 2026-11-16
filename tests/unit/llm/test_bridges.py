"""Bridges from the legacy sync code (LangChain chains, StructuredLLM) onto the LLM gateway."""

import asyncio
import re
import threading
from decimal import Decimal
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel
from structlog.testing import capture_logs

from app.adapters.llm._sync import run_sync
from app.adapters.llm.langchain_bridge import GatewayChatModel
from app.adapters.llm.legacy_structured import GatewayStructuredLLM
from app.config.settings import AppSettings, ConfigError
from app.container import LEGACY_CHAIN_ROUTES, Container
from app.pipeline.chains import Chains, build_chains
from app.ports.llm import LLMRequest, LLMResult, Usage
from app.ports.llm_errors import LLMBadRequest, LLMOutputInvalid, LLMThrottled
from tests.fakes.fake_chat_model import RoutingFakeChatModel

ROOT = Path(__file__).resolve().parents[3]


class _Doc(BaseModel):
    title: str = ""


class RecordingGateway:
    def __init__(self, output: object = "reply", stop: str = "end", error=None) -> None:
        self.output, self.stop, self.error = output, stop, error
        self.requests: list[LLMRequest] = []

    async def complete(self, req, cancel=None):
        self.requests.append(req)
        if self.error is not None:
            raise self.error
        return LLMResult(
            output=self.output,
            usage=Usage(input_tokens=1, output_tokens=1),
            cost_usd=Decimal(0),
            provider="fake",
            model="fake-1",
            latency_ms=1,
            repaired=False,
            stop_reason=self.stop,
            attempts=1,
        )


async def _value(v: int) -> int:
    await asyncio.sleep(0)
    return v


async def _boom() -> None:
    raise LLMThrottled("x")


def test_run_sync_without_loop():
    assert run_sync(_value(3)) == 3
    with pytest.raises(LLMThrottled):
        run_sync(_boom())


def test_run_sync_inside_running_loop():
    async def outer() -> tuple[int, int]:
        loop_thread = threading.get_ident()
        seen: list[int] = []

        async def inner() -> int:
            seen.append(threading.get_ident())
            return 7

        return run_sync(inner()), int(seen[0] != loop_thread)

    assert asyncio.run(outer()) == (7, 1)


def test_chat_bridge_maps_messages_and_step():
    gw = RecordingGateway("hello")
    model = GatewayChatModel(gateway=gw, step="rewrite", prompt_id="legacy.rewrite")
    msgs = [
        SystemMessage(content="sys one"),
        SystemMessage(content="sys two"),
        HumanMessage(content="q1"),
        AIMessage(content="a1"),
        HumanMessage(content="q2"),
    ]
    out = model.invoke(msgs)
    assert out.content == "hello"
    req = gw.requests[0]
    assert (req.step, req.metadata.prompt_id, req.output_schema) == (
        "rewrite",
        "legacy.rewrite",
        None,
    )
    assert req.system == "sys one\n\nsys two"
    assert [(m.role, m.content) for m in req.messages] == [
        ("user", "q1"),
        ("assistant", "a1"),
        ("user", "q2"),
    ]


def test_chat_bridge_works_in_a_prompt_chain():
    gw = RecordingGateway("chained")
    model = GatewayChatModel(gateway=gw, step="jd_extract", prompt_id="legacy.quick_jd")
    chain = PromptTemplate.from_template("JD: {jd}") | model | StrOutputParser()
    assert chain.invoke({"jd": "text"}) == "chained"
    assert [(m.role, m.content) for m in gw.requests[0].messages] == [("user", "JD: text")]


def test_chat_bridge_rejects_assistant_last_message():
    model = GatewayChatModel(gateway=RecordingGateway(), step="rewrite", prompt_id="legacy.x")
    with pytest.raises(LLMBadRequest, match="last message"):
        model.invoke([HumanMessage(content="q"), AIMessage(content="prefill")])


def test_bridge_logs_truncation():
    gw = RecordingGateway("partial", stop="max_tokens")
    model = GatewayChatModel(gateway=gw, step="rewrite", prompt_id="legacy.rewrite")
    with capture_logs() as logs:
        assert model.invoke("secret prompt").content == "partial"
    hits = [e for e in logs if e["event"] == "llm.truncated"]
    assert hits and hits[0]["step"] == "rewrite" and hits[0]["prompt_id"] == "legacy.rewrite"
    assert "secret prompt" not in str(logs) and "partial" not in str(logs)


def test_structured_bridge_returns_model():
    gw = RecordingGateway(_Doc(title="t"))
    llm = GatewayStructuredLLM(gw)  # type: ignore[arg-type]
    assert llm.invoke_structured("parse this", _Doc) == _Doc(title="t")
    req = gw.requests[0]
    assert (req.step, req.metadata.prompt_id, req.output_schema) == (
        "profile_import",
        "legacy.profile_import",
        _Doc,
    )
    assert [(m.role, m.content) for m in req.messages] == [("user", "parse this")]


def test_structured_bridge_invalid_returns_default():
    gw = RecordingGateway(error=LLMOutputInvalid("bad json"))
    llm = GatewayStructuredLLM(gw)  # type: ignore[arg-type]
    with capture_logs() as logs:
        assert llm.invoke_structured("secret cv", _Doc) == _Doc()
    assert any(e["event"] == "llm.structured_default" for e in logs)
    assert "secret cv" not in str(logs)
    gw.error = LLMThrottled("busy")
    with pytest.raises(LLMThrottled):
        llm.invoke_structured("x", _Doc)


def test_build_chains_accepts_single_model_and_factory():
    one = RoutingFakeChatModel(default="x")
    single = build_chains(one)
    assert all(getattr(single, f).middle[0] is one for f in Chains.__dataclass_fields__)
    asked: list[str] = []

    def factory(chain: str) -> RoutingFakeChatModel:
        asked.append(chain)
        return RoutingFakeChatModel(default=chain)

    chains = build_chains(factory)
    assert sorted(asked) == sorted(Chains.__dataclass_fields__)
    assert chains.quick_jd.invoke({"job_description": "jd"}) == "quick_jd"


def _fake_settings() -> AppSettings:
    return AppSettings(_env_file=None, llm={"default_provider": "fake"})


def test_container_wires_legacy_chains_to_routes(monkeypatch):
    import app.container as mod

    captured: list[Chains] = []
    real = mod.build_chains

    def spy(llm):
        captured.append(real(llm))
        return captured[-1]

    monkeypatch.setattr(mod, "build_chains", spy)
    c = Container(_fake_settings())
    _ = c.pipeline
    assert set(LEGACY_CHAIN_ROUTES) == set(Chains.__dataclass_fields__)
    for chain, step in LEGACY_CHAIN_ROUTES.items():
        model = getattr(captured[0], chain).middle[0]
        assert isinstance(model, GatewayChatModel)
        assert (model.step, model.prompt_id) == (step, f"legacy.{chain}")
        assert model.gateway is c.llm


def test_container_shares_one_router_and_embeddings_are_fake():
    c = Container(_fake_settings())
    assert c.llm is c.llm
    assert c.embeddings.name == "fake"
    assert isinstance(c.make_llm_client(), GatewayStructuredLLM)


def test_container_default_embeddings_are_titan_without_network():
    c = Container(AppSettings(_env_file=None))
    assert c.embeddings.name == "bedrock_titan"


def test_two_sequential_run_sync_calls_share_the_router():
    c = Container(_fake_settings())
    llm = c.make_llm_client()
    from app.domain.cv.universal_cv import UniversalCVStructured

    first = llm.invoke_structured("cv one", UniversalCVStructured)
    second = llm.invoke_structured("cv two", UniversalCVStructured)
    assert first == second
    recs = c.usage_sink.records()  # type: ignore[attr-defined]
    assert [(r.status, r.provider) for r in recs] == [("ok", "fake"), ("ok", "fake")]


def test_create_app_fails_on_unpriced_model():
    from app.main import create_app

    settings = AppSettings(
        _env_file=None, llm={"default_provider": "bedrock", "default_model": "unpriced-9"}
    )
    with pytest.raises(ConfigError) as info:
        create_app(Container(settings))
    msg = str(info.value)
    assert "jd_extract" in msg and "unpriced-9" in msg and "llm_prices.yaml" in msg


def test_validate_llm_config_is_offline_and_returns_table():
    table = Container(AppSettings(_env_file=None)).validate_llm_config()
    assert table.resolve("rewrite").provider == "bedrock"


_PIPELINE_IMPORT = re.compile(r"^\s*(from|import) app\.(pipeline|api)\b", re.M)
_LANGCHAIN_IMPORT = re.compile(r"^\s*(from|import) langchain", re.M)


def test_adapters_import_no_pipeline_and_only_the_bridge_imports_langchain():
    offenders = []
    for path in (ROOT / "app" / "adapters").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if _PIPELINE_IMPORT.search(text):
            offenders.append(f"pipeline:{path.name}")
        if _LANGCHAIN_IMPORT.search(text) and path.name != "langchain_bridge.py":
            offenders.append(f"langchain:{path.name}")
    assert offenders == []
