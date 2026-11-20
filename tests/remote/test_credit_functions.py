"""credits_grant / reserve / settle / tier_upgrade against the real SQL, as app_backend."""

from collections.abc import Callable

import pytest
from psycopg.errors import RaiseException

from app.domain.common import uuid7
from tests.remote._helpers import (
    Conn,
    assert_invariant,
    balance,
    grant,
    insert_session,
    ledger_count,
    new_key,
    reserve,
    scalar,
    settle,
    tier_upgrade,
)
from tests.remote._rest import DENIED, Rest


def _raises(code: str):
    return pytest.raises(RaiseException, match=code)


@pytest.fixture
def funded(user_a, backend_conn: Conn) -> tuple[str, str]:
    """(user_id, session_id) with 100 credits granted."""
    grant(backend_conn, user_a.id, 100, new_key("fund"))
    return user_a.id, insert_session(backend_conn, user_a.id)


def test_grant_then_replay_same_key_returns_same_balance(user_a, backend_conn: Conn) -> None:
    key = new_key("grant")
    assert grant(backend_conn, user_a.id, 40, key) == 40
    assert grant(backend_conn, user_a.id, 40, key) == 40
    assert balance(backend_conn, user_a.id) == (40, 0)
    assert ledger_count(backend_conn, user_a.id) == 1
    assert_invariant(backend_conn, user_a.id)


# Validation runs before any lookup, so random ids are enough here.
CALLS: dict[str, Callable[[Conn, str | None], object]] = {
    "grant": lambda c, k: grant(c, uuid7(), 1, k),
    "reserve": lambda c, k: reserve(c, uuid7(), uuid7(), 1, k),
    "settle": lambda c, k: settle(c, uuid7(), 0, k),
    "tier_upgrade": lambda c, k: tier_upgrade(c, uuid7(), uuid7(), 1, k),
}


@pytest.mark.parametrize("fn", list(CALLS))
@pytest.mark.parametrize("key", [None, "", "   "], ids=["null", "empty", "blank"])
def test_blank_idempotency_key_rejected(backend_conn: Conn, fn: str, key: str | None) -> None:
    with _raises("INVALID_IDEMPOTENCY_KEY") as exc:
        CALLS[fn](backend_conn, key)
    assert exc.value.sqlstate == "P0001"


def test_idempotency_mismatch_cross_kind_and_cross_user(funded, user_b, backend_conn) -> None:
    uid, sid = funded
    key = new_key("mismatch")
    grant(backend_conn, uid, 10, key, kind="adjustment")
    before = balance(backend_conn, uid), ledger_count(backend_conn, uid)
    with _raises("IDEMPOTENCY_MISMATCH"):
        grant(backend_conn, uid, 10, key, kind="purchase")  # same user, other kind
    with _raises("IDEMPOTENCY_MISMATCH"):
        grant(backend_conn, user_b.id, 10, key, kind="adjustment")  # other user
    with _raises("IDEMPOTENCY_MISMATCH"):
        reserve(backend_conn, uid, sid, 5, key)  # a grant key replayed as a reserve
    with _raises("IDEMPOTENCY_MISMATCH"):
        tier_upgrade(backend_conn, uid, sid, 5, key)
    res_key = new_key("mismatch-res")
    reserve(backend_conn, uid, sid, 5, res_key)
    with _raises("IDEMPOTENCY_MISMATCH"):
        reserve(backend_conn, user_b.id, sid, 5, res_key)  # other user's reserve key
    assert balance(backend_conn, user_b.id) == (0, 0)
    assert (balance(backend_conn, uid)[0], ledger_count(backend_conn, uid)) == (
        before[0][0],
        before[1] + 1,
    )
    assert_invariant(backend_conn, uid)


def test_reserve_insufficient_raises_p0001(funded, backend_conn: Conn) -> None:
    uid, sid = funded
    with _raises("INSUFFICIENT_CREDITS") as exc:
        reserve(backend_conn, uid, sid, 101, new_key("big"))
    assert exc.value.sqlstate == "P0001"
    # The failed call rolled back its ledger row too.
    assert ledger_count(backend_conn, uid) == 1
    assert assert_invariant(backend_conn, uid) == (100, 0)


def test_settle_capture_bounds(funded, backend_conn: Conn) -> None:
    uid, sid = funded
    res = reserve(backend_conn, uid, sid, 30, new_key("bounds"))
    with _raises("INVALID_AMOUNT"):
        settle(backend_conn, res, 31, new_key("over"))
    with _raises("INVALID_AMOUNT"):
        settle(backend_conn, res, -1, new_key("neg"))
    with _raises("RESERVATION_NOT_FOUND"):
        settle(backend_conn, uuid7(), 0, new_key("missing"))
    settle(backend_conn, res, 30, new_key("ok"))
    with _raises("RESERVATION_SETTLED"):
        settle(backend_conn, res, 0, new_key("again"))  # a different key cannot re-settle
    assert assert_invariant(backend_conn, uid) == (70, 0)


@pytest.mark.parametrize(
    ("capture", "status"), [(30, "captured"), (12, "partial"), (0, "released")]
)
def test_settle_keeps_invariant_and_replay_is_noop(
    funded, backend_conn: Conn, capture: int, status: str
) -> None:
    uid, sid = funded
    res = reserve(backend_conn, uid, sid, 30, new_key("settle"))
    assert assert_invariant(backend_conn, uid) == (100, 30)
    key = new_key("settle-key")
    settle(backend_conn, res, capture, key)
    after = assert_invariant(backend_conn, uid)
    assert after == (100 - capture, 0)
    count = ledger_count(backend_conn, uid)
    settle(backend_conn, res, capture, key)  # replay: no-op
    assert assert_invariant(backend_conn, uid) == after
    assert ledger_count(backend_conn, uid) == count
    row = backend_conn.execute(
        "select status, captured from public.credit_reservations where id = %s", (res,)
    ).fetchone()
    assert row is not None and (row["status"], row["captured"]) == (status, capture)


def test_invariant_sum_matches_balance(funded, backend_conn: Conn) -> None:
    uid, sid = funded
    res = reserve(backend_conn, uid, sid, 30, new_key("inv-r"))
    settle(backend_conn, res, 20, new_key("inv-s"))
    assert tier_upgrade(backend_conn, uid, sid, 10, new_key("inv-t")) == 70
    grant(backend_conn, uid, 5, new_key("inv-g"), kind="purchase")
    reserve(backend_conn, uid, sid, 15, new_key("inv-open"))
    assert assert_invariant(backend_conn, uid) == (75, 15)
    with _raises("INSUFFICIENT_CREDITS"):
        tier_upgrade(backend_conn, uid, sid, 61, new_key("inv-big"))  # 75 - 15 held = 60
    assert assert_invariant(backend_conn, uid) == (75, 15)


def test_bonus_kind_marks_profile(user_a, backend_conn: Conn) -> None:
    grant(backend_conn, user_a.id, 100, f"signup_bonus:{user_a.id}", kind="signup_bonus")
    sql = "select bonus_granted_at is not null from public.profiles where user_id = %s"
    assert scalar(backend_conn, sql, (user_a.id,)) is True


RPCS: dict[str, dict[str, object]] = {
    "credits_grant": {"p_user": None, "p_amount": 1, "p_kind": "adjustment", "p_idem": "x"},
    "credits_reserve": {"p_user": None, "p_session": None, "p_amount": 1, "p_idem": "x"},
    "credits_settle": {"p_reservation": None, "p_capture": 0, "p_idem": "x"},
    "credits_tier_upgrade": {
        "p_user": None,
        "p_session": None,
        "p_from": "a",
        "p_to": "b",
        "p_amount": 1,
        "p_idem": "x",
    },
    "claim_signup_bonus": {
        "p_user": None,
        "p_ip_bucket": "x",
        "p_dev_bucket": None,
        "p_ip_max": 3,
        "p_dev_max": 1,
        "p_amount": 100,
    },
    "prune_checkpoints": {},
    "user_email_verified": {"p_user": None},
}


@pytest.fixture(scope="module")
def rpc_caller(session_users):
    """One confirmed user for every authenticated RPC case (not one per case)."""
    return session_users(confirmed=True)


@pytest.mark.parametrize("actor", ["anon", "authenticated"])
@pytest.mark.parametrize("fn", list(RPCS))
def test_functions_not_executable_by_authenticated(
    anon_rest: Rest, rest, request: pytest.FixtureRequest, fn: str, actor: str
) -> None:
    """RPC refused for lack of EXECUTE: 401 (anon) / 403 (authenticated). A 404 is NOT
    accepted: PostgREST lists every public function in its schema cache regardless of
    privileges, so PGRST202 would mean a missing function or a signature drift.

    Ids are random, so even a wrongly executable function could not touch a real user."""
    if actor == "anon":
        api = anon_rest
    else:
        api = rest(request.getfixturevalue("rpc_caller"))
    args = {k: (uuid7() if v is None and k != "p_dev_bucket" else v) for k, v in RPCS[fn].items()}
    resp = api.rpc(fn, args)
    assert resp.status_code in DENIED, f"{actor} ran {fn}: HTTP {resp.status_code}"
    assert "PGRST202" not in resp.text
