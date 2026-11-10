"""PipelineService: runs, inspects and resumes the compiled graph (implements PipelineRunner)."""

from typing import Any

from langgraph.graph.state import CompiledStateGraph

from app.pipeline.state import CombinedState

JsonDict = dict[str, Any]


class PipelineService:
    def __init__(self, graph: CompiledStateGraph, max_iterations: int = 2) -> None:
        self._graph = graph
        self._max_iterations = max_iterations

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
        """Start a fresh pipeline run. Returns final state dict."""
        config: Any = {"configurable": {"thread_id": thread_id}}

        initial_state: CombinedState = {
            "job_description": job_description,
            "user_resume": user_resume_text,
            "detected_domain": "general",
            "quick_jd": None,
            "quick_cv": None,
            "eligibility_verdict": None,
            "is_eligible": False,
            "eligibility_message": None,
            "structured_jd": None,
            "structured_cv": None,
            "final_match": None,
            "re_write_cv": None,
            "counter": 0,
            "max_iterations": self._max_iterations,
            "gaps_identified": [],
            "user_qna": None,
            "hitl_session_id": thread_id,
            "hitl_awaiting_input": False,
            "cover_letter_requested": cover_letter_requested,
            "cover_letter_tone": cover_letter_tone,
            "cover_letter_length": cover_letter_length,
            "cover_letter_result": None,
            "cover_letter_hitl_done": False,
        }

        return self._graph.invoke(initial_state, config)

    def get_state(self, thread_id: str) -> JsonDict:
        """Return current pipeline state; checks for HITL pause."""
        config: Any = {"configurable": {"thread_id": thread_id}}
        state = self._graph.get_state(config)

        if not state:
            return {"status": "not_found"}

        is_paused_at_hitl = bool(state.next and "hitl_node" in state.next)

        return {
            "values": state.values,
            "is_paused_at_hitl": is_paused_at_hitl,
            "next": list(state.next) if state.next else [],
        }

    def resume(self, thread_id: str, user_qna: str) -> JsonDict:
        """Inject HITL answers and resume execution to completion."""
        config: Any = {"configurable": {"thread_id": thread_id}}
        self._graph.update_state(config, {"user_qna": user_qna})

        for _ in self._graph.stream(None, config):
            pass

        return self._graph.get_state(config).values

    def resume_cover_letter(self, thread_id: str, tone: str, length: str) -> JsonDict:
        """Inject cover letter options (tone+length) and resume execution."""
        config: Any = {"configurable": {"thread_id": thread_id}}
        self._graph.update_state(
            config,
            {
                "cover_letter_tone": tone,
                "cover_letter_length": length,
            },
        )

        for _ in self._graph.stream(None, config):
            pass

        return self._graph.get_state(config).values
