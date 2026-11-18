"""Per-call LLM usage record and the sink that persists it."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel

from app.ports.llm import Usage


class LlmCallRecord(BaseModel, frozen=True):
    at: datetime
    step: str
    prompt_id: str
    prompt_version: int
    provider: str
    model: str
    status: Literal["ok", "error", "cancelled"]
    error_kind: str | None
    usage: Usage
    cost_usd: Decimal
    latency_ms: int
    attempts: int
    repaired: bool
    fallback_used: bool
    user_id: str | None = None
    session_id: str | None = None
    job_id: str | None = None


class UsageSink(Protocol):
    def write(self, record: LlmCallRecord) -> None: ...
