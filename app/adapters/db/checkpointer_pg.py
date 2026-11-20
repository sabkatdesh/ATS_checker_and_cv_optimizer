"""LangGraph checkpoints in Postgres schema `lg` (ADR-007). Never logs the DSN.

The library hard-codes unqualified table names, so every connection it uses has `lg` on its
search_path:
- runs: a fresh AsyncConnection per run, opened inside run_sync's loop (nothing loop-bound is
  shared across calls). search_path is set with a plain SET after connecting rather than the
  `options` startup parameter, which poolers may reject.
- reads and deletes: a connection from the shared sync pool, with `set local search_path`, so the
  setting ends with that checkout's transaction and never leaks to other repos on the pool.
"""

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager, contextmanager
from typing import Any, cast

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.base import SerializerProtocol
from psycopg import AsyncConnection, Connection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool
from pydantic import SecretStr

from app.pipeline.checkpoint_types import checkpoint_serde

SEARCH_PATH_SQL = "set search_path = lg"
LOCAL_SEARCH_PATH_SQL = "set local search_path = lg"
STATEMENT_TIMEOUT_SQL = "select set_config('statement_timeout', %s, false)"
APPLICATION_NAME = "cv-checkpointer"

AsyncConnect = Callable[..., Awaitable[AsyncConnection[DictRow]]]


class _PooledReader(BaseCheckpointSaver[str]):
    """Sync, read-mostly saver: each call borrows one pool connection scoped to schema lg."""

    def __init__(self, pool: ConnectionPool, serde: SerializerProtocol) -> None:
        super().__init__(serde=serde)
        self._pool = pool
        self._serde = serde

    @contextmanager
    def _saver(self) -> Iterator[PostgresSaver]:
        with self._pool.connection() as conn:
            conn.execute(LOCAL_SEARCH_PATH_SQL)  # opens the checkout's transaction
            yield PostgresSaver(cast(Connection[DictRow], conn), serde=self._serde)

    def get_tuple(self, config: Any) -> CheckpointTuple | None:
        with self._saver() as saver:
            return saver.get_tuple(config)

    def list(
        self,
        config: Any,
        *,
        filter: dict[str, Any] | None = None,  # noqa: A002 - library signature
        before: Any = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        with self._saver() as saver:
            rows = list(saver.list(config, filter=filter, before=before, limit=limit))
        return iter(rows)

    def delete_thread(self, thread_id: str) -> None:
        with self._saver() as saver:
            saver.delete_thread(thread_id)

    def put(
        self,
        config: Any,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> Any:
        raise NotImplementedError("the reader never writes; runs use open_async()")

    def put_writes(
        self, config: Any, writes: Sequence[tuple[str, Any]], task_id: str, task_path: str = ""
    ) -> None:
        raise NotImplementedError("the reader never writes; runs use open_async()")


class PostgresCheckpointerFactory:
    def __init__(
        self,
        dsn: SecretStr,
        pool: ConnectionPool,
        *,
        connect_timeout_s: float = 10,
        statement_timeout_ms: int = 15000,
        connect: AsyncConnect | None = None,
    ) -> None:
        self._dsn = dsn
        self._connect: AsyncConnect = connect or AsyncConnection.connect
        self._connect_timeout = max(1, int(connect_timeout_s))
        self._statement_timeout_ms = int(statement_timeout_ms)
        self._serde = checkpoint_serde()
        self._reader = _PooledReader(pool, self._serde)

    @asynccontextmanager
    async def _open(self) -> AsyncIterator[BaseCheckpointSaver]:
        conn = await self._connect(
            self._dsn.get_secret_value(),
            autocommit=True,
            prepare_threshold=None,
            row_factory=dict_row,
            connect_timeout=self._connect_timeout,
            application_name=APPLICATION_NAME,
        )
        async with conn:
            await conn.execute(SEARCH_PATH_SQL)
            await conn.execute(STATEMENT_TIMEOUT_SQL, (str(self._statement_timeout_ms),))
            yield AsyncPostgresSaver(conn, serde=self._serde)

    def open_async(self) -> AbstractAsyncContextManager[BaseCheckpointSaver]:
        return self._open()

    def reader(self) -> BaseCheckpointSaver:
        return self._reader

    def delete_thread(self, thread_id: str) -> None:
        self._reader.delete_thread(thread_id)
