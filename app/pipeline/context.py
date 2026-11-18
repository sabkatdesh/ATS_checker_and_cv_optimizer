"""Per-run context handed to every step."""

from dataclasses import dataclass, field

from app.pipeline.hooks import NodeHooks, NoopHooks, ProgressMark
from app.ports.llm import CancelToken


@dataclass(frozen=True)
class RunContext:
    session_id: str
    cancel: CancelToken
    hooks: NodeHooks = field(default_factory=NoopHooks)
    progress: ProgressMark = field(default_factory=ProgressMark, compare=False)
