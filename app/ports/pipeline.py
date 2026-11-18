from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from app.pipeline.hooks import NodeHooks
    from app.pipeline.state import RunOptions
    from app.pipeline.summary import SessionSummary

JsonDict = dict[str, Any]


class PipelineRunner(Protocol):
    def run(
        self,
        *,
        job_description: str,
        user_resume_text: str,
        thread_id: str,
        options: "RunOptions",
        hooks: "NodeHooks | None" = None,
    ) -> JsonDict: ...

    def get_state(self, thread_id: str) -> JsonDict: ...  # {"values", "next", "interrupt"}

    def resume(
        self,
        thread_id: str,
        reply: Mapping[str, Any] | str | None,
        *,
        hooks: "NodeHooks | None" = None,
    ) -> JsonDict: ...

    def resume_cover_letter(
        self, thread_id: str, tone: str, length: str, *, hooks: "NodeHooks | None" = None
    ) -> JsonDict: ...

    def summary(self, thread_id: str) -> "SessionSummary | None": ...

    def cancel(self, thread_id: str) -> bool: ...
