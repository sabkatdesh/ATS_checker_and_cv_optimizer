"""Per-run context handed to every step."""

from dataclasses import dataclass

from app.ports.llm import CancelToken


@dataclass(frozen=True)
class RunContext:
    session_id: str
    cancel: CancelToken
