"""Target-safety checks of the remote suite, offline (mock connections, no DB, no network)."""

from contextlib import contextmanager
from typing import Any

import psycopg
import pytest

from tests.remote._auth_admin import TestUser
from tests.remote._env import RemoteEnv
from tests.remote._gate import (
    DEV_PROJECT_REF,
    PROJECT_MESSAGE,
    ROLE_MESSAGE,
    UnsafeTarget,
    check_backend_role,
    preflight,
    project_problem,
    project_ref,
    role_problem,
)
from tests.remote._helpers import denied_attempt

REF = "abcdefghijklmnopqrst"
GOOD_ROW = {
    "role": "app_backend",
    "session_role": "app_backend",
    "is_super": False,
    "owns_tables": False,
}


def _env(url: str = f"https://{REF}.supabase.co", dsn: str | None = None) -> RemoteEnv:
    dsn = dsn or f"postgresql://app_backend.{REF}:pw@aws-0-x.pooler.supabase.com:5432/postgres"
    return RemoteEnv(
        _env_file=None,  # type: ignore[call-arg]
        DB__DSN=dsn,
        AUTH__SUPABASE_URL=url,
        SUPABASE_SECRET_KEY="sk",
        SUPABASE_PUBLISHABLE_KEY="pk",
    )


class _Conn:
    def __init__(self, row: dict[str, Any] | None = None, fail: Exception | None = None) -> None:
        self.row, self.fail = row, fail
        self.sql: list[str] = []
        self.rolled_back = 0
        self.committed = 0

    def execute(self, sql: str, params: Any = None) -> "_Conn":
        self.sql.append(sql)
        if self.fail:
            raise self.fail
        return self

    def fetchone(self) -> dict[str, Any] | None:
        return self.row

    @contextmanager
    def transaction(self):
        try:
            yield
        except BaseException:
            self.rolled_back += 1
            raise
        self.committed += 1


@pytest.mark.parametrize(
    ("patch", "problem"),
    [
        ({}, None),
        ({"role": "postgres", "session_role": "postgres"}, "not app_backend"),
        ({"session_role": "postgres"}, "not app_backend"),  # SET ROLE from another login
        ({"is_super": True}, "superuser"),
        ({"owns_tables": True}, "owns tables (grants would not bind it)"),
    ],
)
def test_role_problem(patch: dict[str, Any], problem: str | None) -> None:
    assert role_problem({**GOOD_ROW, **patch}) == problem


def test_role_problem_without_a_row() -> None:
    assert role_problem(None) == "role not found"


def test_check_backend_role_accepts_app_backend_and_rejects_owner() -> None:
    check_backend_role(_Conn(GOOD_ROW))
    with pytest.raises(UnsafeTarget, match="app_backend"):
        check_backend_role(_Conn({**GOOD_ROW, "role": "postgres", "session_role": "postgres"}))


def test_preflight_exits_when_role_is_unsafe() -> None:
    def probe(_env: RemoteEnv) -> None:
        check_backend_role(_Conn({**GOOD_ROW, "is_super": True}))

    with pytest.raises(pytest.exit.Exception) as exc:
        preflight(True, _env, probe, ref=REF)
    assert str(exc.value).startswith(ROLE_MESSAGE)


def test_preflight_passes_for_dev_app_backend() -> None:
    env = preflight(True, _env, lambda e: check_backend_role(_Conn(GOOD_ROW)), ref=REF)
    assert env is not None


@pytest.mark.parametrize(
    ("url", "dsn", "problem"),
    [
        (f"https://{REF}.supabase.co", None, None),
        (f"https://{REF}.supabase.co", f"postgresql://app_backend:pw@db.{REF}.supabase.co/x", None),
        ("https://otherprojectref0000.supabase.co", None, "url"),
        (
            f"https://{REF}.supabase.co",
            "postgresql://app_backend.prodref:pw@pooler.example/x",
            "dsn",
        ),
        (f"https://{REF}.supabase.co", "not a dsn = = =", "dsn"),
    ],
)
def test_project_problem(url: str, dsn: str | None, problem: str | None) -> None:
    assert project_problem(_env(url, dsn), REF) == problem


def test_preflight_exits_for_another_project_before_connecting() -> None:
    def probe(_env: RemoteEnv) -> None:
        raise AssertionError("must not connect")

    with pytest.raises(pytest.exit.Exception) as exc:
        preflight(True, lambda: _env("https://prodprojectref00000.supabase.co"), probe, ref=REF)
    assert str(exc.value) == PROJECT_MESSAGE


def test_project_ref_defaults_to_the_dev_constant() -> None:
    assert project_ref({}) == DEV_PROJECT_REF
    assert project_ref({"M4_PROJECT_REF": " other "}) == "other"


def test_denied_attempt_never_commits_a_success() -> None:
    conn = _Conn(GOOD_ROW)
    denied_attempt(conn, "truncate public.credit_ledger")  # type: ignore[arg-type]
    assert (conn.rolled_back, conn.committed) == (1, 0)


def test_denied_attempt_propagates_the_refusal() -> None:
    conn = _Conn(fail=psycopg.errors.InsufficientPrivilege("permission denied"))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        denied_attempt(conn, "truncate public.credit_ledger")  # type: ignore[arg-type]
    assert (conn.rolled_back, conn.committed) == (1, 0)


def test_test_user_repr_hides_the_password() -> None:
    user = TestUser(id="u", email="m4test+x@example.test", password="pw-secret", confirmed=True)
    assert "pw-secret" not in repr(user)
