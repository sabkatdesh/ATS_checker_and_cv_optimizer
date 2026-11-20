"""SQL helpers for the remote suite: app_backend connections, credit calls, invariants, threads.

Every connection here is app_backend (the DB__DSN role) in autocommit, so each statement is
its own transaction, exactly like the app's pool checkouts.
"""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import psycopg
from psycopg.rows import DictRow, dict_row

from app.domain.common import uuid7

Conn = psycopg.Connection[DictRow]
CONNECT_TIMEOUT_S = 5
APPLICATION_NAME = "m4-remote-tests"


def connect_backend(dsn: str, timeout_s: int = CONNECT_TIMEOUT_S) -> Conn:
    # prepare_threshold=None: safe behind a pooler; the session pooler also tolerates it.
    return psycopg.connect(
        dsn,
        autocommit=True,
        prepare_threshold=None,
        row_factory=dict_row,
        connect_timeout=timeout_s,
        application_name=APPLICATION_NAME,
    )


def one(conn: Conn, sql: str, params: Any = None) -> dict[str, Any]:
    row = conn.execute(sql, params).fetchone()
    assert row is not None
    return dict(row)


def scalar(conn: Conn, sql: str, params: Any = None) -> Any:
    return next(iter(one(conn, sql, params).values()))


# ─── Credit functions ────────────────────────────────────────────────────────────


def grant(conn: Conn, uid: str, amount: int, key: str | None, kind: str = "adjustment") -> int:
    return int(
        scalar(conn, "select public.credits_grant(%s, %s, %s, %s)", (uid, amount, kind, key))
    )


def reserve(conn: Conn, uid: str, sid: str, amount: int, key: str | None) -> str:
    sql = "select public.credits_reserve(%s, %s, %s, %s)::text"
    return str(scalar(conn, sql, (uid, sid, amount, key)))


def settle(conn: Conn, res: str, capture: int, key: str | None) -> None:
    conn.execute("select public.credits_settle(%s, %s, %s)", (res, capture, key))


def tier_upgrade(conn: Conn, uid: str, sid: str, amount: int, key: str | None) -> int:
    sql = "select public.credits_tier_upgrade(%s, %s, 'standard', 'premium', %s, %s)"
    return int(scalar(conn, sql, (uid, sid, amount, key)))


def balance(conn: Conn, uid: str) -> tuple[int, int]:
    row = conn.execute(
        "select balance, held from public.credit_balances where user_id = %s", (uid,)
    ).fetchone()
    return (int(row["balance"]), int(row["held"])) if row else (0, 0)


def ledger_sums(conn: Conn, uid: str) -> tuple[int, int]:
    row = one(
        conn,
        "select coalesce(sum(delta_balance), 0)::int as b, coalesce(sum(delta_held), 0)::int as h "
        "from public.credit_ledger where user_id = %s",
        (uid,),
    )
    return int(row["b"]), int(row["h"])


def assert_invariant(conn: Conn, uid: str) -> tuple[int, int]:
    """sum(delta_balance) == balance and sum(delta_held) == held; returns (balance, held)."""
    bal = balance(conn, uid)
    assert ledger_sums(conn, uid) == bal
    return bal


def ledger_count(conn: Conn, uid: str) -> int:
    return int(scalar(conn, "select count(*) from public.credit_ledger where user_id = %s", (uid,)))


def new_key(label: str) -> str:
    return f"m4test:{label}:{uuid7()}"


# ─── Rows ────────────────────────────────────────────────────────────────────────


def insert_session(conn: Conn, uid: str, status: str = "draft") -> str:
    sid = uuid7()
    conn.execute(
        "insert into public.cv_sessions (id, user_id, status) values (%s, %s, %s)",
        (sid, uid, status),
    )
    return sid


def lg_counts(conn: Conn, thread_id: str) -> dict[str, int]:
    out = {}
    for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
        sql = f"select count(*) from lg.{table} where thread_id = %s"  # noqa: S608 - fixed names
        out[table] = int(scalar(conn, sql, (thread_id,)))
    return out


def insert_checkpoint_rows(conn: Conn, thread_id: str) -> None:
    """One row in each lg table, shaped as the library writes them (content is irrelevant)."""
    conn.execute(
        "insert into lg.checkpoints (thread_id, checkpoint_id, checkpoint) "
        "values (%s, 'm4test-c1', '{}'::jsonb)",
        (thread_id,),
    )
    conn.execute(
        "insert into lg.checkpoint_blobs (thread_id, channel, version, type, blob) "
        "values (%s, 'm4test', '1', 'empty', null)",
        (thread_id,),
    )
    conn.execute(
        "insert into lg.checkpoint_writes (thread_id, checkpoint_id, task_id, idx, channel, blob) "
        "values (%s, 'm4test-c1', 't1', 0, 'm4test', '\\x00'::bytea)",
        (thread_id,),
    )


# ─── Concurrency ─────────────────────────────────────────────────────────────────


def run_parallel[T](n: int, dsn: str, fn: Callable[[Conn, int], T]) -> list[T | BaseException]:
    """Run fn(conn, i) on n threads, each with its own connection, released together."""
    gate = threading.Barrier(n, timeout=30)

    def worker(i: int) -> T | BaseException:
        try:
            with connect_backend(dsn, timeout_s=10) as conn:
                gate.wait()
                return fn(conn, i)
        except BaseException as exc:  # noqa: BLE001 - collected and asserted by the caller
            return exc

    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(worker, range(n)))


def raised(results: list[Any], code: str) -> int:
    """How many results are a psycopg RaiseException carrying `code`."""
    return sum(
        1 for r in results if isinstance(r, psycopg.errors.RaiseException) and code in str(r)
    )
