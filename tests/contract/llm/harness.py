"""Provider-agnostic contract harness: scripted outcomes in, provider-native bodies out.

Each adapter adds one harness class in harnesses/ and appends it to HARNESSES in test_contract.py.
"""

from dataclasses import dataclass, field
from typing import Protocol

from app.adapters.llm._breaker import BreakerRegistry
from app.adapters.llm._pricing import PriceTable
from app.adapters.llm._retry import RetryPolicy
from app.ports.llm import LLMProvider, Usage

CONTRACT_PROMPT_ID = "contract.test"


@dataclass(frozen=True)
class Ok:
    text: str
    usage: Usage = field(default_factory=lambda: Usage(input_tokens=10, output_tokens=5))


@dataclass(frozen=True)
class Throttle:
    retry_after: float | None = None


@dataclass(frozen=True)
class ServerError:
    pass


@dataclass(frozen=True)
class Timeout:
    pass


@dataclass(frozen=True)
class Refusal:
    pass


@dataclass(frozen=True)
class Hang:
    seconds: float


@dataclass(frozen=True)
class BadRequest:
    pass


@dataclass(frozen=True)
class Empty:
    pass


@dataclass(frozen=True)
class Truncated:
    text: str


Outcome = Ok | Throttle | ServerError | Timeout | Refusal | Hang | BadRequest | Empty | Truncated


class ContractHarness(Protocol):
    name: str
    supports_native: bool

    def provider(
        self, prices: PriceTable, breakers: BreakerRegistry, retry: RetryPolicy
    ) -> LLMProvider: ...

    def script(self, *outcomes: Outcome) -> None: ...

    def sent_bodies(self) -> list[dict]: ...

    def last_roles(self) -> list[str]: ...
