"""Typed pipeline failures. Messages are constant: a step name and a code, never user text."""

from typing import Literal

from app.pipeline.hooks import Stage

ErrorCode = Literal[
    "LLM_OUTPUT_INVALID",
    "CONTENT_REFUSED",
    "LLM_UNAVAILABLE",
    "LLM_BAD_REQUEST",
    "LLM_AUTH",
    "PROFILE_INCOMPLETE",
    "INTERNAL",
]


class PipelineStepFailed(Exception):
    """A required step failed; the job ends and the user is refunded by the system."""

    def __init__(self, step: str, code: ErrorCode, refund: str = "SYSTEM") -> None:
        self.step = step
        self.code: ErrorCode = code
        self.refund = refund
        super().__init__(f"{step} failed: {code}")


class NotAwaitingInput(Exception):
    """A reply arrived for a thread that is not paused at the gap questions."""

    detail = "Session is not waiting for your input"

    def __init__(self) -> None:
        super().__init__(self.detail)


class PipelineCancelled(Exception):
    """The run was cancelled at a node boundary or during a node's LLM call."""

    detail = "Run cancelled"

    def __init__(self, node: str, stage: Stage, when: Literal["before", "during", "after"]) -> None:
        self.node = node
        self.stage: Stage = stage
        self.when: Literal["before", "during", "after"] = when
        super().__init__(f"{node} cancelled {when}")
