"""RLS + grants through PostgREST, for every table in MATRIX x op x caller.

Callers: anon (publishable key, no JWT), user_b acting on A's rows, user_a on their own rows.
Client roles have no write grants anywhere, so every write must be refused (401/403) or touch
zero rows; reads follow MATRIX. Backend checks confirm nothing changed underneath.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest

from tests.remote._helpers import Conn, balance, scalar
from tests.remote._rest import DENIED, Rest, denied_or_empty, rows
from tests.remote._seed import Seeded, cleanup_leftovers, seed_user_rows
from tests.rls_matrix import MATRIX, Access

OPS = ("select", "insert", "update", "delete")
ACTORS = ("anon", "user_b", "user_a")


@dataclass
class World:
    seeded: Seeded
    callers: dict[str, Rest]


@pytest.fixture(scope="module")
def world(session_users, backend_conn: Conn, rest: Callable, anon_rest: Rest) -> Iterator[World]:
    a = session_users(confirmed=True)
    b = session_users(confirmed=True)
    seeded = seed_user_rows(backend_conn, a.id)
    try:
        yield World(seeded, {"anon": anon_rest, "user_b": rest(b), "user_a": rest(a)})
    finally:
        cleanup_leftovers(backend_conn, seeded)


def _access(table: str, actor: str) -> Access:
    rule = MATRIX[table]
    return rule.anon if actor == "anon" else rule.authenticated


def _backend_count(conn: Conn, table: str, filters: dict[str, str]) -> int:
    assert table in MATRIX and all(c.isidentifier() for c in filters)  # fixed identifiers
    where = " and ".join(f"{col}::text = %s" for col in filters)
    sql = f"select count(*) from public.{table} where {where}"  # noqa: S608
    return int(scalar(conn, sql, tuple(filters.values())))


CASES = [(t, op, actor) for t in MATRIX for op in OPS for actor in ACTORS]


@pytest.mark.parametrize(("table", "op", "actor"), CASES, ids=["-".join(c) for c in CASES])
def test_rls_matrix(world: World, backend_conn: Conn, table: str, op: str, actor: str) -> None:
    api = world.callers[actor]
    filters = world.seeded.filters[table]
    before = _backend_count(backend_conn, table, filters)
    assert before >= 1, "seed row missing"
    access = _access(table, actor)

    if op == "select":
        resp = api.select(table, **filters)
        if access == "none":
            assert resp.status_code in DENIED, f"{actor} read {table}: HTTP {resp.status_code}"
        elif access == "select_own" and actor == "user_a":
            assert resp.status_code == 200 and len(rows(resp)) >= 1
        else:
            # select_own seen by someone else, or select_active on an inactive row: nothing.
            assert resp.status_code == 200 and rows(resp) == []
        return

    if op == "insert":
        resp = api.insert(table, dict(filters))
        assert resp.status_code in DENIED, f"{actor} inserted into {table}: {resp.status_code}"
    elif op == "update":
        resp = api.update(table, dict(filters), **filters)
        assert denied_or_empty(resp), f"{actor} updated {table}: HTTP {resp.status_code}"
    else:
        resp = api.delete(table, **filters)
        assert denied_or_empty(resp), f"{actor} deleted from {table}: HTTP {resp.status_code}"
    assert _backend_count(backend_conn, table, filters) == before


def test_user_cannot_update_own_credit_balance(world: World, backend_conn: Conn) -> None:
    uid = world.seeded.user_id
    before = balance(backend_conn, uid)
    resp = world.callers["user_a"].update("credit_balances", {"balance": 1_000_000}, user_id=uid)
    assert denied_or_empty(resp)
    assert balance(backend_conn, uid) == before


def test_user_b_sees_none_of_a_rows_unfiltered(world: World) -> None:
    """No filter at all: everything B can list belongs to B (never to A)."""
    a = world.seeded.user_id
    for table, rule in MATRIX.items():
        if rule.authenticated != "select_own" or table == "job_events":
            continue
        listed = rows(world.callers["user_b"].select(table))
        assert all(r.get("user_id") != a for r in listed), table


def test_anon_sees_only_active_templates(world: World) -> None:
    resp = world.callers["anon"].select("templates")
    assert resp.status_code == 200
    listed = rows(resp)
    assert listed and all(r["is_active"] for r in listed)
    assert world.seeded.filters["templates"]["id"] not in {r["id"] for r in listed}
    assert "classic" in {r["id"] for r in listed}
