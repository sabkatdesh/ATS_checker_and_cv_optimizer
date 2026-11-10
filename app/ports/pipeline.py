from typing import Any, Protocol

JsonDict = dict[str, Any]


class PipelineRunner(Protocol):
    def run(
        self,
        *,
        job_description: str,
        user_resume_text: str,
        thread_id: str,
        cover_letter_requested: bool = False,
        cover_letter_tone: str | None = None,
        cover_letter_length: str | None = None,
    ) -> JsonDict: ...

    def get_state(self, thread_id: str) -> JsonDict: ...

    def resume(self, thread_id: str, user_qna: str) -> JsonDict: ...

    def resume_cover_letter(self, thread_id: str, tone: str, length: str) -> JsonDict: ...
