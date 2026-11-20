"""Smoke races on credits_reserve (M5 owns the formal race suite). Separate connections per
thread, released together by a barrier."""

from tests.remote._helpers import (
    Conn,
    assert_invariant,
    grant,
    insert_session,
    new_key,
    raised,
    reserve,
    run_parallel,
    scalar,
)


def test_concurrent_same_key_reserve_yields_one_reservation(user_a, backend_conn: Conn, dsn):
    uid = user_a.id
    grant(backend_conn, uid, 100, new_key("race-fund"))
    sid = insert_session(backend_conn, uid)
    key = new_key("race-same")
    results = run_parallel(8, dsn, lambda conn, _i: reserve(conn, uid, sid, 10, key))
    assert not [r for r in results if isinstance(r, BaseException)]
    assert len(set(results)) == 1  # every caller got the one reservation id
    count = scalar(
        backend_conn, "select count(*) from public.credit_reservations where user_id = %s", (uid,)
    )
    assert count == 1
    assert assert_invariant(backend_conn, uid) == (100, 10)


def test_concurrent_reserves_never_overdraw(user_a, backend_conn: Conn, dsn):
    uid = user_a.id
    grant(backend_conn, uid, 100, new_key("race-fund"))
    sid = insert_session(backend_conn, uid)
    # 20 reserves of 10 against 100 available, on 10 connections (2 each): the session pooler
    # on a small dev compute caps client connections around 15, so 20 sockets could be refused.

    def two(conn: Conn, i: int) -> list[str | BaseException]:
        out: list[str | BaseException] = []
        for j in range(2):
            try:
                out.append(reserve(conn, uid, sid, 10, new_key(f"race-{i}-{j}")))
            except Exception as exc:  # noqa: BLE001 - counted below
                out.append(exc)
        return out

    nested = run_parallel(10, dsn, two)
    assert not [r for r in nested if isinstance(r, BaseException)]
    results = [r for batch in nested if isinstance(batch, list) for r in batch]
    assert len(results) == 20
    ok = [r for r in results if isinstance(r, str)]
    assert len(ok) == 10
    assert raised(results, "INSUFFICIENT_CREDITS") == 10
    assert assert_invariant(backend_conn, uid) == (100, 100)
