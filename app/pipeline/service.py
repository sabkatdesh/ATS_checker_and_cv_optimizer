"""PipelineService: runs, inspects and resumes the compiled graph (implements PipelineRunner)."""

from collections.abc import Mapping
from typing import Any

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from app.adapters.llm._sync import run_sync
from app.pipeline.errors import ErrorCode, NotAwaitingInput, PipelineCancelled, PipelineStepFailed
from app.pipeline.hooks import NodeHooks, Stage
from app.pipeline.runs import RunRegistry
from app.pipeline.state import PipelineState, RunOptions
from app.pipeline.summary import SessionSummary, summarize

JsonDict = dict[str, Any]


def _config(thread_id: str) -> Any:
    return {"configurable": {"thread_id": thread_id}}


class PipelineService:
    def __init__(self, graph: CompiledStateGraph, runs: RunRegistry) -> None:
        """`runs` must be the registry the graph was built with (`deps.runs`)."""
        self._graph = graph
        self._runs = runs
        # A failed or cancelled node leaves no checkpoint write, so the outcome is kept here.
        self._failures: dict[str, ErrorCode] = {}
        self._cancelled: dict[str, Stage] = {}

    def _invoke(self, payload: Any, thread_id: str, hooks: NodeHooks | None) -> JsonDict:
        self._runs.open(thread_id, hooks)
        try:
            run_sync(self._graph.ainvoke(payload, _config(thread_id)))
        except PipelineStepFailed as failure:
            self._failures[thread_id] = failure.code
            raise
        except PipelineCancelled as cancelled:
            self._cancelled[thread_id] = cancelled.stage
            raise
        finally:
            self._runs.close(thread_id)
        self._failures.pop(thread_id, None)
        self._cancelled.pop(thread_id, None)
        return dict(self._graph.get_state(_config(thread_id)).values)

    def run(
        self,
        *,
        job_description: str,
        user_resume_text: str,
        thread_id: str,
        options: RunOptions,
        hooks: NodeHooks | None = None,
    ) -> JsonDict:
        """Start a fresh run; returns the state values (paused or finished)."""
        initial: PipelineState = {
            "session_id": thread_id,
            "jd_text": job_description,
            "cv_text": user_resume_text,
            "options": options,
            "passes": 0,
            "warnings": [],
        }
        return self._invoke(initial, thread_id, hooks)

    def get_state(self, thread_id: str) -> JsonDict:
        snapshot = self._graph.get_state(_config(thread_id))
        interrupts = snapshot.interrupts
        return {
            "values": dict(snapshot.values),
            "next": list(snapshot.next),
            "interrupt": interrupts[0].value if interrupts else None,
        }

    def resume(
        self,
        thread_id: str,
        reply: Mapping[str, Any] | str | None,
        *,
        hooks: NodeHooks | None = None,
    ) -> JsonDict:
        """Answer the gap questions and run to the next pause or the end."""
        if "await_answers" not in self._graph.get_state(_config(thread_id)).next:
            raise NotAwaitingInput
        # langgraph ignores a None resume and misreads {} as a map of interrupt ids; both mean
        # "nothing to say", which the node turns into skipped answers.
        return self._invoke(Command(resume=reply or ""), thread_id, hooks)

    def resume_cover_letter(
        self, thread_id: str, tone: str, length: str, *, hooks: NodeHooks | None = None
    ) -> JsonDict:
        return self._invoke(Command(resume={"tone": tone, "length": length}), thread_id, hooks)

    def cancel(self, thread_id: str) -> bool:
        """Cancel a running or paused thread; False when there is nothing to cancel.

        A paused thread is marked, so its next resume stops before any node runs.
        """
        if self._runs.cancel(thread_id):
            return True
        if not self._graph.get_state(_config(thread_id)).next:
            return False
        self._runs.open(thread_id)
        return self._runs.cancel(thread_id)

    def summary(self, thread_id: str) -> SessionSummary | None:
        return summarize(
            self._graph.get_state(_config(thread_id)).values,
            self._failures.get(thread_id),
            self._cancelled.get(thread_id),
        )
