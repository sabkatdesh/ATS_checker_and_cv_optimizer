"""LangGraph checkpoints in schema lg on the real database (ADR-007)."""

from collections.abc import Iterator

import pytest
from langgraph.checkpoint.postgres.base import BasePostgresSaver

from app.adapters.background.inline_runner import InlineRunner
from app.config.settings import AppSettings
from app.container import Container
from app.domain.common import uuid7
from app.domain.cv.rewrite import RewrittenCV
from app.pipeline.state import RunOptions
from tests.fakes.fake_renderers import FakeCoverLetterRenderer, FakePdfRenderer
from tests.integration.test_pipeline_offline_fake import JD, _profile
from tests.remote._helpers import Conn, insert_checkpoint_rows, insert_session, lg_counts, scalar
from tests.remote._rest import Rest

LG_TABLES = {"checkpoint_migrations", "checkpoints", "checkpoint_blobs", "checkpoint_writes"}


def _container(dsn: str) -> Container:
    """A fresh container: its own pool and its own PostgresCheckpointerFactory."""
    settings = AppSettings(
        _env_file=None, env="test", llm={"default_provider": "fake"}, db={"dsn": dsn}
    )
    return Container(
        settings,
        runner=InlineRunner(),
        pdf_factory=FakePdfRenderer,
        cover_letter_factory=FakeCoverLetterRenderer,
    )


def test_lg_tables_exist(backend_conn: Conn) -> None:
    found = {
        r["table_name"]
        for r in backend_conn.execute(
            "select table_name from information_schema.tables where table_schema = 'lg'"
        ).fetchall()
    }
    assert LG_TABLES <= found


def test_setup_has_nothing_to_apply(backend_conn: Conn) -> None:
    """setup() applies MIGRATIONS[v+1:] where v is the highest recorded version; every version
    is recorded by 1000, so it would apply nothing (setup() itself is never run: it needs DDL)."""
    versions = {
        int(r["v"])
        for r in backend_conn.execute("select v from lg.checkpoint_migrations").fetchall()
    }
    assert versions == set(range(len(BasePostgresSaver.MIGRATIONS)))


@pytest.fixture
def paused_thread(user_a, backend_conn: Conn) -> Iterator[str]:
    """A live (awaiting_input) session row, so a concurrent prune spares its thread."""
    tid = insert_session(backend_conn, user_a.id, status="awaiting_input")
    yield tid
    for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
        sql = f"delete from lg.{table} where thread_id = %s"  # noqa: S608 - fixed names
        backend_conn.execute(sql, (tid,))


def test_pause_survives_new_container(paused_thread: str, dsn: str, backend_conn: Conn) -> None:
    tid = paused_thread
    c1 = _container(dsn)
    try:
        c1.pipeline.run(job_description=JD, profile=_profile(), thread_id=tid, options=RunOptions())
        assert c1.pipeline.get_state(tid)["next"] == ["await_answers"]
    finally:
        c1.close()
    assert lg_counts(backend_conn, tid)["checkpoints"] > 0  # it is in Postgres, not memory

    c2 = _container(dsn)
    try:
        state = c2.pipeline.get_state(tid)
        assert state["next"] == ["await_answers"]
        assert state["interrupt"]["type"] == "gap_questions"
        final = c2.pipeline.resume(tid, "I have used Kubernetes for two years.")
        assert isinstance(final["tailored_cv"], RewrittenCV)
        assert c2.pipeline.get_state(tid)["next"] == []
    finally:
        c2.close()


def test_prune_removes_terminal_threads(user_a, backend_conn: Conn) -> None:
    """NOTE: prune_checkpoints is global; on the dev project it also sweeps any other
    terminal, stale or orphaned thread, which is exactly its job."""
    uid = user_a.id
    terminal = insert_session(backend_conn, uid, status="succeeded")
    paused = insert_session(backend_conn, uid, status="awaiting_input")
    stale = uuid7()
    backend_conn.execute(
        "insert into public.cv_sessions (id, user_id, status, updated_at) "
        "values (%s, %s, 'awaiting_input', now() - interval '30 days')",
        (stale, uid),
    )
    orphan = uuid7()  # no cv_sessions row at all
    for tid in (terminal, paused, stale, orphan):
        insert_checkpoint_rows(backend_conn, tid)

    deleted = scalar(backend_conn, "select public.prune_checkpoints()")
    assert deleted >= 3

    gone = {"checkpoints": 0, "checkpoint_blobs": 0, "checkpoint_writes": 0}
    assert lg_counts(backend_conn, terminal) == gone
    assert lg_counts(backend_conn, stale) == gone
    assert lg_counts(backend_conn, orphan) == gone
    assert lg_counts(backend_conn, paused) == {k: 1 for k in gone}
    for table in gone:
        sql = f"delete from lg.{table} where thread_id = %s"  # noqa: S608 - fixed names
        backend_conn.execute(sql, (paused,))


def test_anon_cannot_read_lg(anon_rest: Rest, rest, user_a, service_rest: Rest) -> None:
    """lg is not an exposed PostgREST schema: no caller, not even the secret key, can reach it
    (PGRST106 -> 406), and there is no public table of that name (404)."""
    for api in (anon_rest, rest(user_a), service_rest):
        for table in LG_TABLES:
            resp = api.select_in_schema("lg", table)
            assert resp.status_code in (400, 401, 403, 404, 406), table
        assert anon_rest.select("checkpoints").status_code in (401, 403, 404)
