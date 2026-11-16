"""LLM provider and gateway ports with the value objects they exchange."""

import asyncio
import threading
from decimal import Decimal
from typing import Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel, Field, field_validator

T = TypeVar("T", bound=BaseModel)


class Message(BaseModel, frozen=True):
    role: Literal["user", "assistant"]
    content: str


class CallMeta(BaseModel, frozen=True):
    prompt_id: str
    prompt_version: int = 0
    user_id: str | None = None
    session_id: str | None = None
    job_id: str | None = None


class Usage(BaseModel, frozen=True):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
        )


class Route(BaseModel, frozen=True):
    step: str
    provider: str
    model: str
    max_tokens: int = Field(gt=0)
    temperature: float | None
    timeout_s: float = Field(gt=0)
    max_attempts: int = 4
    structured_mode: Literal["native", "prompt"]
    stream: bool = False


class LLMRequest(BaseModel, Generic[T]):  # noqa: UP046
    step: str
    system: str = ""
    messages: list[Message] = Field(min_length=1)
    output_schema: type[T] | None = None
    cache_prefix: bool = False
    metadata: CallMeta

    @field_validator("messages")
    @classmethod
    def _last_message_is_user(cls, v: list[Message]) -> list[Message]:
        if v[-1].role != "user":
            raise ValueError("last message must have role 'user'")
        return v


class LLMResult(BaseModel, Generic[T]):  # noqa: UP046
    output: T | str
    usage: Usage
    cost_usd: Decimal
    provider: str
    model: str
    latency_ms: int
    repaired: bool
    stop_reason: str
    attempts: int
    fallback_used: bool = False


class CancelToken:
    """Cooperative cancellation flag, safe to set from any thread or event loop."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    async def wait(self, poll_s: float = 0.05) -> None:
        while not self._event.is_set():
            await asyncio.sleep(poll_s)


class LLMProvider(Protocol):
    name: str

    async def complete(
        self, req: LLMRequest[T], route: Route, cancel: CancelToken
    ) -> LLMResult[T]: ...


class LLMGateway(Protocol):
    async def complete(
        self, req: LLMRequest[T], cancel: CancelToken | None = None
    ) -> LLMResult[T]: ...
