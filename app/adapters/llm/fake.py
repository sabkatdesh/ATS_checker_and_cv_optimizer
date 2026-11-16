"""Offline LLM provider: scripted outcomes, canned legacy responses, schema default instances.

Deterministic and network-free, so the pipeline and the contract suite can run without a model.
"""

import asyncio
import contextvars
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from app.adapters.llm._base import BaseProvider, RawCompletion, Stop, WireRequest
from app.adapters.llm._breaker import BreakerRegistry
from app.adapters.llm._pricing import PriceTable
from app.adapters.llm._retry import RetryPolicy
from app.ports.llm import CancelToken, LLMRequest, LLMResult, Route, T, Usage
from app.ports.llm_errors import LLMError

DEFAULT_DIR = Path(__file__).parent / "fake_responses"
_SAFE_KEY = re.compile(r"^[A-Za-z0-9_.\-]+$")
_current: contextvars.ContextVar["_CallInfo | None"] = contextvars.ContextVar(
    "fake_call", default=None
)


@dataclass
class Reply:
    text: str
    stop: str = "end"
    usage: Usage = field(default_factory=lambda: Usage(input_tokens=10, output_tokens=5))


@dataclass
class Fail:
    error: type[LLMError]
    retry_after_s: float | None = None


@dataclass
class Hang:
    seconds: float


FakeOutcome = Reply | Fail | Hang


@dataclass(frozen=True)
class _CallInfo:
    key: str
    schema: type[BaseModel] | None


def _example(node: Any, defs: dict[str, Any]) -> Any:
    """Smallest value satisfying a JSON-schema node (required fields only)."""
    if "$ref" in node:
        return _example(defs[node["$ref"].rsplit("/", 1)[-1]], defs)
    if "default" in node:
        return node["default"]
    for union in ("anyOf", "oneOf"):
        if union in node:
            options = [o for o in node[union] if o.get("type") != "null"]
            return _example(options[0], defs) if options else None
    if "enum" in node:
        return node["enum"][0]
    if "allOf" in node:
        return _example(node["allOf"][0], defs)
    kind = node.get("type")
    if kind == "object":
        props = node.get("properties", {})
        return {k: _example(props[k], defs) for k in node.get("required", []) if k in props}
    return {
        "string": "",
        "integer": 0,
        "number": 0.0,
        "boolean": False,
        "array": [],
        "null": None,
    }.get(kind)


def default_instance(schema: type[BaseModel]) -> BaseModel:
    try:
        return schema()
    except ValidationError:
        raw = schema.model_json_schema()
        return schema.model_validate(_example(raw, raw.get("$defs", {})))


class FakeTransport:
    name = "fake"
    supports_native_schema = True

    def __init__(
        self,
        script: dict[str, list[FakeOutcome]] | None = None,
        *,
        defaults_dir: Path | None = DEFAULT_DIR,
        latency_s: float = 0.0,
    ) -> None:
        self._script: dict[str, list[FakeOutcome]] = defaultdict(list)
        for key, outcomes in (script or {}).items():
            self._script[key] = list(outcomes)
        self._defaults_dir = defaults_dir
        self._latency_s = latency_s
        self.sent: list[WireRequest] = []

    def push(self, key: str, *outcomes: FakeOutcome) -> None:
        self._script[key].extend(outcomes)

    async def send(self, wire: WireRequest, cancel: CancelToken) -> RawCompletion:
        self.sent.append(wire)
        info = _current.get()
        key = info.key if info else ""
        if self._latency_s > 0:
            await asyncio.sleep(self._latency_s)
        queue = self._script.get(key)
        if queue:
            outcome = queue.pop(0)
            if isinstance(outcome, Fail):
                raise outcome.error("fake failure", retry_after_s=outcome.retry_after_s)
            if isinstance(outcome, Reply):
                stop: Stop = outcome.stop  # type: ignore[assignment]
                return RawCompletion(outcome.text, stop, outcome.stop, outcome.usage)
            await asyncio.sleep(outcome.seconds)  # Hang: cancelled from outside via the caller
        usage = Usage(input_tokens=10, output_tokens=5)
        return RawCompletion(self._default_text(info), "end", "end", usage)

    def _default_text(self, info: "_CallInfo | None") -> str:
        key = info.key if info else ""
        if self._defaults_dir is not None and _SAFE_KEY.match(key):
            path = self._defaults_dir / f"{key}.json"
            if path.is_file():
                return path.read_text(encoding="utf-8")
        if info and info.schema is not None:
            return default_instance(info.schema).model_dump_json()
        return "{}"


class FakeProvider(BaseProvider):
    def __init__(self, transport: FakeTransport, **kwargs: Any) -> None:
        super().__init__(transport, **kwargs)
        self.transport = transport

    async def complete(self, req: LLMRequest[T], route: Route, cancel: CancelToken) -> LLMResult[T]:
        key = req.metadata.prompt_id or req.step
        token = _current.set(_CallInfo(key, req.output_schema))
        try:
            return await super().complete(req, route, cancel)
        finally:
            _current.reset(token)


def build_fake_provider(
    *,
    prices: PriceTable,
    breakers: BreakerRegistry,
    retry: RetryPolicy = RetryPolicy(),  # noqa: B008 - frozen dataclass, safe default
    script: dict[str, list[FakeOutcome]] | None = None,
) -> FakeProvider:
    return FakeProvider(FakeTransport(script), prices=prices, breakers=breakers, retry=retry)


__all__ = [
    "DEFAULT_DIR",
    "Fail",
    "FakeOutcome",
    "FakeProvider",
    "FakeTransport",
    "Hang",
    "Reply",
    "build_fake_provider",
]
