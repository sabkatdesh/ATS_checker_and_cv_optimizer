"""Checkpointer factories: per-run async savers, a shared reader and thread deletion (no DB)."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import psycopg
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic import SecretStr

from app.adapters.db.checkpointer_pg import SEARCH_PATH_SQL, PostgresCheckpointerFactory
from app.adapters.llm._sync import run_sync
from app.domain.cv.rewrite import RewrittenCV
from app.domain.match.schemas import Eligibility
from app.domain.questions.schemas import GapQuestion, GapQuestions
from app.domain.trust.judge import JudgeFindings
from app.pipeline.checkpoint_types import allowed_modules
from app.pipeline.checkpointer import MemoryCheckpointerFactory
from app.pipeline.graph import build_state_graph
from app.pipeline.service import PipelineService
from app.pipeline.state import RunOptions
from tests.pipeline.helpers import deps_for, persona_profile, tech_jd

DSN = SecretStr("postgresql://app_backend:pw@db.invalid:5432/postgres")


def _replies() -> dict:
    return {
        "jd_extract": [tech_jd()],
        "eligibility": [Eligibility(score=60, gaps=["Kubernetes depth"])],
        "gap_questions": [GapQuestions(questions=[GapQuestion(id="q1", text="K8s?")])],
        "rewrite": [RewrittenCV(), RewrittenCV()],
        "verify_claims": [JudgeFindings()],
    }


def _start(svc: PipelineService, tid: str = "t1") -> dict:
    return svc.run(
        job_description="jd text",
        profile={**persona_profile(), "summary": "cv text"},
        thread_id=tid,
        options=RunOptions(),
    )


def test_memory_factory_round_trip_resume():
    """A paused thread resumes in a second service instance that shares the factory."""
    factory = MemoryCheckpointerFactory()
    _, deps = deps_for(_replies())
    first = PipelineService(build_state_graph(deps), deps.runs, factory)
    _start(first)
    assert first.get_state("t1")["next"] == ["await_answers"]

    second = PipelineService(build_state_graph(deps), deps.runs, factory)
    assert second.get_state("t1")["next"] == ["await_answers"]
    final = second.resume("t1", "answers")
    assert final["answers"].free_text == "answers"
    assert second.get_state("t1")["next"] == []
    factory.delete_thread("t1")
    assert second.get_state("t1") == {"values": {}, "next": [], "interrupt": None}


class _RecordingSaver(MemorySaver):
    def __init__(self, serde):
        super().__init__(serde=serde)
        self.aputs = 0

    async def aput(self, config, checkpoint, metadata, new_versions):
        self.aputs += 1
        return await super().aput(config, checkpoint, metadata, new_versions)


class _RecordingFactory(MemoryCheckpointerFactory):
    def __init__(self):
        super().__init__()
        self.saver = _RecordingSaver(self._saver.serde)
        self._saver = self.saver
        self.opened: list[asyncio.AbstractEventLoop] = []

    def open_async(self):
        @asynccontextmanager
        async def cm():
            self.opened.append(asyncio.get_running_loop())
            yield self.saver

        return cm()


def test_service_compiles_per_run_with_factory_saver():
    factory = _RecordingFactory()
    _, deps = deps_for(_replies())
    svc = PipelineService(build_state_graph(deps), deps.runs, factory)
    assert factory.opened == []  # building the service opens no run saver
    _start(svc)
    after_run = factory.saver.aputs
    assert len(factory.opened) == 1 and after_run > 0
    svc.resume("t1", "answers")
    assert len(factory.opened) == 2 and factory.saver.aputs > after_run
    assert factory.opened[0] is not factory.opened[1]  # each run_sync call has its own loop


def _fake_async_connect(calls: list):
    async def connect(conninfo, **kwargs):
        conn = MagicMock(spec=psycopg.AsyncConnection)
        conn.__aenter__.return_value = conn
        calls.append(SimpleNamespace(conninfo=conninfo, kwargs=kwargs, conn=conn))
        return conn

    return connect


def test_async_saver_is_opened_inside_the_run_sync_loop():
    calls: list = []
    factory = PostgresCheckpointerFactory(DSN, MagicMock(), connect=_fake_async_connect(calls))
    seen: list = []

    async def go():
        async with factory.open_async() as saver:
            seen.append((saver, asyncio.get_running_loop()))

    run_sync(go())
    run_sync(go())
    assert len(calls) == 2  # a fresh connection per run, never a loop-bound shared pool
    (s1, loop1), (s2, loop2) = seen
    assert isinstance(s1, AsyncPostgresSaver) and s1.loop is loop1
    assert s2.loop is loop2 and loop1 is not loop2
    for call in calls:
        assert call.conninfo == DSN.get_secret_value()
        assert call.kwargs["autocommit"] is True
        assert call.kwargs["prepare_threshold"] is None
        assert "options" not in call.kwargs  # search_path is set after connecting (pooler-safe)
        call.conn.execute.assert_any_await(SEARCH_PATH_SQL)
        call.conn.__aexit__.assert_awaited()


def test_search_path_is_set_after_connect_before_use():
    assert SEARCH_PATH_SQL == "set search_path = lg"


class _FakePool:
    def __init__(self):
        self.conn = MagicMock(spec=psycopg.Connection)
        self.checkouts = 0

    def connection(self):
        pool = self

        class _Ctx:
            def __enter__(self):
                pool.checkouts += 1
                return pool.conn

            def __exit__(self, *exc):
                return False

        return _Ctx()


def _cursor(conn):
    return conn.cursor.return_value.__enter__.return_value


def test_delete_thread_issues_three_deletes_with_bound_thread_id():
    pool = _FakePool()
    factory = PostgresCheckpointerFactory(DSN, pool, connect=_fake_async_connect([]))
    factory.delete_thread("sess-1")
    pool.conn.execute.assert_called_once_with("set local search_path = lg")
    statements = [c.args for c in _cursor(pool.conn).execute.call_args_list]
    assert statements == [
        ("DELETE FROM checkpoints WHERE thread_id = %s", ("sess-1",)),
        ("DELETE FROM checkpoint_blobs WHERE thread_id = %s", ("sess-1",)),
        ("DELETE FROM checkpoint_writes WHERE thread_id = %s", ("sess-1",)),
    ]


def test_reader_scopes_search_path_to_one_checkout():
    pool = _FakePool()
    _cursor(pool.conn).fetchone.return_value = None
    reader = PostgresCheckpointerFactory(DSN, pool, connect=_fake_async_connect([])).reader()
    assert reader.get_tuple({"configurable": {"thread_id": "t9"}}) is None
    assert pool.checkouts == 1
    pool.conn.execute.assert_called_once_with("set local search_path = lg")
    sql, params = _cursor(pool.conn).execute.call_args.args
    assert "from checkpoints" in sql.lower() and "t9" in params


def _allow(serde) -> object:
    assert isinstance(serde, JsonPlusSerializer)
    return serde._allowed_msgpack_modules


def test_serde_allowlist_reused(monkeypatch):
    want = _allow(JsonPlusSerializer(allowed_msgpack_modules=allowed_modules()))
    pool = _FakePool()
    factory = PostgresCheckpointerFactory(DSN, pool, connect=_fake_async_connect([]))
    savers: list = []

    async def go():
        async with factory.open_async() as saver:
            savers.append(saver)

    run_sync(go())
    assert _allow(savers[0].serde) == want
    assert _allow(factory.reader().serde) == want
    built: list = []
    real_init = PostgresSaver.__init__

    def spy(self, conn, pipe=None, serde=None):
        built.append(serde)
        real_init(self, conn, pipe, serde)

    monkeypatch.setattr(PostgresSaver, "__init__", spy)
    factory.delete_thread("x")
    assert _allow(built[0]) == want
    assert _allow(MemoryCheckpointerFactory().reader().serde) == want
