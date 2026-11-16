from app.adapters.llm._breaker import BreakerRegistry
from app.adapters.llm._pricing import PriceTable
from app.adapters.llm._retry import RetryPolicy
from app.adapters.llm.fake import (
    Fail,
    FakeOutcome,
    FakeProvider,
    Reply,
    build_fake_provider,
)
from app.adapters.llm.fake import Hang as FakeHang
from app.ports.llm import Usage
from app.ports.llm_errors import LLMBadRequest, LLMThrottled, LLMTimeout, LLMUnavailable
from tests.contract.llm import harness as h


def _translate(o: h.Outcome) -> FakeOutcome:
    match o:
        case h.Ok(text, usage):
            return Reply(text, usage=usage)
        case h.Throttle(retry_after):
            return Fail(LLMThrottled, retry_after_s=retry_after)
        case h.ServerError():
            return Fail(LLMUnavailable)
        case h.Timeout():
            return Fail(LLMTimeout)
        case h.Refusal():
            return Reply("", stop="refused", usage=Usage())
        case h.Hang(seconds):
            return FakeHang(seconds)
        case h.BadRequest():
            return Fail(LLMBadRequest)
        case h.Empty():
            return Reply("")
        case h.Truncated(text):
            return Reply(text, stop="max_tokens")
    raise AssertionError(f"unknown outcome {o!r}")


class FakeHarness:
    name = "fake"
    supports_native = True

    def __init__(self) -> None:
        self._pending: list[FakeOutcome] = []
        self._provider: FakeProvider | None = None

    def provider(
        self, prices: PriceTable, breakers: BreakerRegistry, retry: RetryPolicy
    ) -> FakeProvider:
        self._provider = build_fake_provider(
            prices=prices,
            breakers=breakers,
            retry=retry,
            script={h.CONTRACT_PROMPT_ID: self._pending},
        )
        self._pending = []
        return self._provider

    def script(self, *outcomes: h.Outcome) -> None:
        translated = [_translate(o) for o in outcomes]
        if self._provider is None:
            self._pending.extend(translated)
        else:
            self._provider.transport.push(h.CONTRACT_PROMPT_ID, *translated)

    def sent_bodies(self) -> list[dict]:
        assert self._provider is not None
        return [
            {
                "model": w.model,
                "system": w.system,
                "max_tokens": w.max_tokens,
                "messages": [{"role": m.role, "content": m.content} for m in w.messages],
                "json_schema": w.json_schema,
            }
            for w in self._provider.transport.sent
        ]

    def last_roles(self) -> list[str]:
        return [m["role"] for m in self.sent_bodies()[-1]["messages"]]
