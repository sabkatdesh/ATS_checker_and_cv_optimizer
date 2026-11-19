"""Recording stand-in for a psycopg pool: captures every SQL string and its params."""

from contextlib import contextmanager
from typing import Any


class _Cursor:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[Any]:
        return list(self._rows)


class RecordingConnection:
    def __init__(self, rows: list[Any], log: list[tuple[str, Any]]) -> None:
        self._rows = rows
        self.log = log

    def execute(self, sql: str, params: Any = None) -> _Cursor:
        self.log.append((sql, params))
        return _Cursor(self._rows)


class RecordingPool:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self.rows = rows or []
        self.log: list[tuple[str, Any]] = []
        self.raise_on_connect: Exception | None = None

    @contextmanager
    def connection(self, timeout: float | None = None):
        if self.raise_on_connect is not None:
            raise self.raise_on_connect
        yield RecordingConnection(self.rows, self.log)
