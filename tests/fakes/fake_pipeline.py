from collections.abc import Mapping
from typing import Any

from app.pipeline.hooks import NodeHooks
from app.pipeline.state import RunOptions
from app.pipeline.summary import SessionSummary


class FakePipeline:
    def __init__(self):
        self.next_nodes: list[str] = []
        self.values: dict = {}
        self.result: dict = {}
        self.summary_value: SessionSummary | None = None
        self.summary_error: Exception | None = None
        self.error: Exception | None = None
        self.calls: list[tuple[str, tuple, dict]] = []
        self.cancel_result = False

    def _enter(self, name, args, kwargs):
        self.calls.append((name, args, kwargs))
        if self.error is not None:
            raise self.error

    def run(
        self,
        *,
        job_description: str,
        profile: Mapping[str, Any],
        thread_id: str,
        options: RunOptions,
        hooks: NodeHooks | None = None,
    ) -> dict:
        kwargs = {
            "job_description": job_description,
            "profile": profile,
            "thread_id": thread_id,
            "options": options,
        }
        self._enter("run", (), kwargs)
        return self.result

    def get_state(self, thread_id: str) -> dict:
        self._enter("get_state", (thread_id,), {})
        return {"values": self.values, "next": self.next_nodes, "interrupt": None}

    def resume(
        self,
        thread_id: str,
        reply: Mapping[str, Any] | str | None,
        *,
        hooks: NodeHooks | None = None,
    ) -> dict:
        self._enter("resume", (thread_id, reply), {})
        return self.result

    def resume_cover_letter(
        self, thread_id: str, tone: str, length: str, *, hooks: NodeHooks | None = None
    ) -> dict:
        self._enter("resume_cover_letter", (thread_id, tone, length), {})
        return self.result

    def summary(self, thread_id: str) -> SessionSummary | None:
        self.calls.append(("summary", (thread_id,), {}))
        if self.summary_error is not None:
            raise self.summary_error
        return self.summary_value

    def cancel(self, thread_id: str) -> bool:
        self.calls.append(("cancel", (thread_id,), {}))
        return self.cancel_result
