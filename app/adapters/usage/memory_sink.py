"""In-memory bounded usage sink for tests and local runs."""

from collections import deque

from app.ports.usage import LlmCallRecord


class MemoryUsageSink:
    def __init__(self, maxlen: int = 1000) -> None:
        self._records: deque[LlmCallRecord] = deque(maxlen=maxlen)

    def write(self, record: LlmCallRecord) -> None:
        self._records.append(record)

    def records(self) -> list[LlmCallRecord]:
        return list(self._records)
