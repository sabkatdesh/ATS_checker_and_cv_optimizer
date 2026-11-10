class FakePipeline:
    def __init__(self):
        self.next_nodes: list[str] = []
        self.values: dict = {}
        self.result: dict = {}
        self.error: Exception | None = None
        self.calls: list[tuple[str, tuple, dict]] = []

    def _enter(self, name, args, kwargs):
        self.calls.append((name, args, kwargs))
        if self.error is not None:
            raise self.error

    def run(self, **kwargs) -> dict:
        self._enter("run", (), kwargs)
        return self.result

    def get_state(self, thread_id: str) -> dict:
        self._enter("get_state", (thread_id,), {})
        return {
            "values": self.values,
            "next": self.next_nodes,
            "is_paused_at_hitl": "hitl" in " ".join(self.next_nodes).lower(),
        }

    def resume(self, thread_id: str, user_qna: str) -> dict:
        self._enter("resume", (thread_id, user_qna), {})
        return self.result

    def resume_cover_letter(self, thread_id: str, tone: str, length: str) -> dict:
        self._enter("resume_cover_letter", (thread_id, tone, length), {})
        return self.result
