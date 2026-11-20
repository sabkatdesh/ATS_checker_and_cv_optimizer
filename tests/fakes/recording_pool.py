"""Recording stand-in for a psycopg pool: captures every SQL string and its params."""

import re
from contextlib import contextmanager
from typing import Any


class _Cursor:
    def __init__(self, rows: list[Any], rowcount: int) -> None:
        self._rows = rows
        self.rowcount = rowcount

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[Any]:
        return list(self._rows)


class RecordingConnection:
    def __init__(self, rows: list[Any], log: list[tuple[str, Any]], rowcount: int = 1) -> None:
        self._rows = rows
        self.log = log
        self._rowcount = rowcount

    def execute(self, sql: str, params: Any = None) -> _Cursor:
        self.log.append((sql, params))
        return _Cursor(self._rows, self._rowcount)


class RecordingPool:
    def __init__(self, rows: list[Any] | None = None, rowcount: int = 1) -> None:
        self.rows = rows or []
        self.rowcount = rowcount
        self.log: list[tuple[str, Any]] = []
        self.raise_on_connect: Exception | None = None

    @contextmanager
    def connection(self, timeout: float | None = None):
        if self.raise_on_connect is not None:
            raise self.raise_on_connect
        yield RecordingConnection(self.rows, self.log, self.rowcount)


_INSERT_COLUMNS = re.compile(r"insert into [\w.]+ \(([^)]*)\)", re.I)


def assert_user_scoped(sql: str) -> None:
    """Inserts must list user_id as a column; everything else must filter on it."""
    insert = _INSERT_COLUMNS.search(sql)
    if insert:
        columns = [c.strip() for c in insert.group(1).split(",")]
        assert "user_id" in columns, sql
    else:
        assert "user_id = %(user_id)s" in sql, sql
