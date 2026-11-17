"""Typed pipeline failures. Messages are constant: a step name and a code, never user text."""

from typing import Literal

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
