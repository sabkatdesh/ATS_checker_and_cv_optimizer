"""Progress hooks around every pipeline node: stages, percentages and the event they receive."""

import threading
from dataclasses import dataclass
from typing import Literal, Protocol

Stage = Literal["analysis", "questions", "rewrite", "verify", "cover_letter"]
Phase = Literal["started", "finished"]

NODE_STAGES: dict[str, tuple[Stage, int]] = {
    "jd_extract": ("analysis", 10),
    "cv_extract": ("analysis", 15),
    "cv_snapshot": ("analysis", 15),
    "eligibility": ("analysis", 25),
    "gap_questions": ("questions", 35),
    "await_answers": ("questions", 40),
    "ats_score": ("rewrite", 45),
    "rewrite": ("rewrite", 70),
    "verify_claims": ("verify", 85),
    "revise_flagged": ("verify", 90),
    "cover_letter_options": ("cover_letter", 92),
    "cover_letter": ("cover_letter", 100),
}


@dataclass(frozen=True)
class ProgressEvent:
    session_id: str
    node: str
    stage: Stage
    phase: Phase
    progress: int


class NodeHooks(Protocol):
    async def before_node(self, event: ProgressEvent) -> None: ...

    async def after_node(self, event: ProgressEvent) -> None: ...


class NoopHooks:
    async def before_node(self, event: ProgressEvent) -> None:
        return None

    async def after_node(self, event: ProgressEvent) -> None:
        return None


class ProgressMark:
    """High-water mark: a loop back to an earlier node (rewrite -> ats_score) never shows less."""

    def __init__(self) -> None:
        self._value = 0
        self._lock = threading.Lock()

    def advance(self, value: int) -> int:
        with self._lock:
            self._value = max(self._value, value)
            return self._value
