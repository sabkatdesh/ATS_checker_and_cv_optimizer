"""Temporary bridge to the legacy pipeline graph (deleted in Task 10).

The legacy import happens inside a method so nothing legacy loads at import time.
"""

import importlib
from typing import Any

JsonDict = dict[str, Any]


class LegacyPipeline:
    def _graph(self) -> Any:
        return importlib.import_module("core.pipeline.graph")

    def run(
        self,
        *,
        job_description: str,
        user_resume_text: str,
        thread_id: str,
        cover_letter_requested: bool = False,
        cover_letter_tone: str | None = None,
        cover_letter_length: str | None = None,
    ) -> JsonDict:
        return self._graph().run_pipeline_for_user(
            job_description=job_description,
            user_resume_text=user_resume_text,
            thread_id=thread_id,
            cover_letter_requested=cover_letter_requested,
            cover_letter_tone=cover_letter_tone,
            cover_letter_length=cover_letter_length,
        )

    def get_state(self, thread_id: str) -> JsonDict:
        return self._graph().get_pipeline_state(thread_id)

    def resume(self, thread_id: str, user_qna: str) -> JsonDict:
        return self._graph().resume_pipeline_for_user(thread_id, user_qna)

    def resume_cover_letter(self, thread_id: str, tone: str, length: str) -> JsonDict:
        return self._graph().resume_cover_letter_for_user(thread_id, tone, length)
