"""Signup bonus: the service over the real repos, and claim_signup_bonus's guards in SQL.

Guard buckets are unique per test (a random pepper or a random bucket name), because the ip
counter is per UTC day and the device counter is for life: reusing a bucket across runs would
make results depend on history. Every bucket a test touches is deleted afterwards.
"""

import secrets
from collections.abc import Iterator

import psycopg
import pytest
from pydantic import SecretStr

from app.adapters.db.credit_repo import PgCreditRepo
from app.adapters.db.guard_repo import PgGuardRepo
from app.adapters.db.profile_repo import PgProfileRepo
from app.config.db_settings import BonusSettings
from app.domain.common import uuid7
from app.domain.credits.bonus import load_disposable_domains, normalize_ip
from app.ports.auth import VerifiedUser
from app.services.signup_bonus import BonusDeps, claim_signup_bonus, guard_hash
from tests.remote._helpers import Conn, assert_invariant, run_parallel, scalar

IP = "203.0.113.7"  # TEST-NET-3


@pytest.fixture
def buckets(backend_conn: Conn) -> Iterator[list[str]]:
    used: list[str] = []
    yield used
    for b in used:
        backend_conn.execute("delete from public.signup_guards where bucket = %s", (b,))


def _bucket(used: list[str], kind: str) -> str:
    b = f"{kind}:m4test-{uuid7()}"
    used.append(b)
    return b


def claim(conn: Conn, uid: str, ip: str, dev: str | None, ip_max: int = 3) -> str:
    sql = "select public.claim_signup_bonus(%s, %s, %s, %s, 1, 100)"
    return str(scalar(conn, sql, (uid, ip, dev, ip_max)))


def _ledger_bonus_rows(conn: Conn, uid: str) -> int:
    sql = "select count(*) from public.credit_ledger where idempotency_key = %s"
    return int(scalar(conn, sql, (f"signup_bonus:{uid}",)))


def test_bonus_unverified_403_then_verified_100_once(
    make_user, auth_admin, backend_pool, backend_conn: Conn, buckets
) -> None:
    """Through the service the route calls; email_not_verified is what the route maps to 403."""
    settings = BonusSettings(hash_pepper=SecretStr(secrets.token_hex(16)))
    deps = BonusDeps(
        PgProfileRepo(backend_pool),
        PgCreditRepo(backend_pool),
        PgGuardRepo(backend_pool),
        settings,
        load_disposable_domains(),
    )
    user = make_user(confirmed=False)
    buckets.append(guard_hash("ip", normalize_ip(IP), settings.hash_pepper))
    buckets.append(guard_hash("device", "m4test-device", settings.hash_pepper))
    me = VerifiedUser(user_id=user.id, email=user.email)

    assert claim_signup_bonus(me, IP, "m4test-device", deps) == ("email_not_verified", 0)
    auth_admin.confirm(user)
    assert claim_signup_bonus(me, IP, "m4test-device", deps) == ("granted", 100)
    assert claim_signup_bonus(me, IP, "m4test-device", deps) == ("already_granted", 100)
    assert _ledger_bonus_rows(backend_conn, user.id) == 1
    assert assert_invariant(backend_conn, user.id) == (100, 0)


def test_claim_sql_outcomes(make_user, auth_admin, backend_conn: Conn, buckets) -> None:
    user = make_user(confirmed=False)
    ip = _bucket(buckets, "ip")
    assert claim(backend_conn, user.id, ip, None) == "email_not_verified"
    auth_admin.confirm(user)
    assert claim(backend_conn, user.id, ip, None) == "granted"
    assert claim(backend_conn, user.id, ip, None) == "already_granted"  # replay
    assert _ledger_bonus_rows(backend_conn, user.id) == 1
    count = scalar(backend_conn, "select count from public.signup_guards where bucket = %s", (ip,))
    assert count == 1  # the replay did not count again


def test_bonus_ip_guard_trips_at_4th(make_user, backend_conn: Conn, buckets) -> None:
    ip = _bucket(buckets, "ip")
    users = [make_user(confirmed=True) for _ in range(4)]
    outcomes = [claim(backend_conn, u.id, ip, _bucket(buckets, "device")) for u in users]
    assert outcomes == ["granted", "granted", "granted", "pending_review"]
    assert _ledger_bonus_rows(backend_conn, users[3].id) == 0
    review = scalar(
        backend_conn,
        "select bonus_review_at is not null from public.profiles where user_id = %s",
        (users[3].id,),
    )
    assert review is True
    # Once flagged, the user stays in review even if the guard later allows it.
    assert claim(backend_conn, users[3].id, _bucket(buckets, "ip"), None) == "pending_review"


def test_bonus_ip_guard_is_atomic_under_concurrency(make_user, backend_conn, dsn, buckets):
    ip = _bucket(buckets, "ip")
    users = [make_user(confirmed=True) for _ in range(6)]
    devices = [_bucket(buckets, "device") for _ in users]
    results = run_parallel(6, dsn, lambda conn, i: claim(conn, users[i].id, ip, devices[i]))
    assert not [r for r in results if isinstance(r, BaseException)]
    assert sorted(results) == ["granted"] * 3 + ["pending_review"] * 3
    count = scalar(backend_conn, "select count from public.signup_guards where bucket = %s", (ip,))
    assert count == 3


def test_bonus_device_bucket_is_lifetime(make_user, backend_conn: Conn, buckets) -> None:
    device = _bucket(buckets, "device")
    first, second = make_user(confirmed=True), make_user(confirmed=True)
    assert claim(backend_conn, first.id, _bucket(buckets, "ip"), device) == "granted"
    # A different ip does not help: the device bucket (day 1970-01-01) is for life.
    assert claim(backend_conn, second.id, _bucket(buckets, "ip"), device) == "pending_review"
    day = scalar(
        backend_conn, "select day::text from public.signup_guards where bucket = %s", (device,)
    )
    assert day == "1970-01-01"


def test_claim_rejects_bad_input(make_user, backend_conn: Conn) -> None:
    with pytest.raises(psycopg.errors.RaiseException, match="INVALID_USER"):
        claim(backend_conn, uuid7(), "ip:m4test-x", None)  # no such profile
    # A real, verified, eligible profile: only the blank-bucket guard can reject this one, so
    # removing that guard would make it grant (and fail the test).
    real = make_user(confirmed=True)
    for blank in ("", "  "):
        with pytest.raises(psycopg.errors.RaiseException, match="INVALID_USER"):
            claim(backend_conn, real.id, blank, None)
    assert _ledger_bonus_rows(backend_conn, real.id) == 0
