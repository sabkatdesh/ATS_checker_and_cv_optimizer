from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
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
    ) -> JsonDict: ...

    def get_state(self, thread_id: str) -> JsonDict: ...  # {"values", "next", "interrupt"}

    def resume(self, thread_id: str, reply: Any) -> JsonDict: ...

    def resume_cover_letter(self, thread_id: str, tone: str, length: str) -> JsonDict: ...

    def summary(self, thread_id: str) -> "SessionSummary | None": ...
