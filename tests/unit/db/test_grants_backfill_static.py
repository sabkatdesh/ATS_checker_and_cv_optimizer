"""Static checks: pre-existing auth users are backfilled, and function/credit grants are tight."""

import re

from tests.unit.db import sqlscan

_SQL = dict(sqlscan.load_migrations())
HOOKS = sqlscan.strip_comments(_SQL["20261121000800_auth_hooks.sql"])
GRANTS = sqlscan.strip_comments(_SQL["20261121000700_rls_grants.sql"])


def _norm(sql: str) -> str:
    return " ".join(sql.split()).lower()


def test_existing_auth_users_get_a_profile_with_their_verification():
    sql = _norm(HOOKS)
    assert (
        "insert into public.profiles (user_id, email_verified_at) "
        "select id, email_confirmed_at from auth.users "
        "on conflict (user_id) do update set email_verified_at = "
        "coalesce(public.profiles.email_verified_at, excluded.email_verified_at);"
    ) in sql


def test_every_profile_gets_a_balance_row():
    sql = _norm(HOOKS)
    assert (
        "insert into public.credit_balances (user_id) select user_id from public.profiles "
        "on conflict (user_id) do nothing;"
    ) in sql
    # The balance backfill must follow the profile backfill (FK on profiles).
    assert sql.index("into public.credit_balances (user_id) select") > sql.index(
        "select id, email_confirmed_at from auth.users"
    )


def test_global_function_default_revokes_public_execute():
    sql = _norm(GRANTS)
    # No `in schema`: only the global default controls the built-in PUBLIC EXECUTE grant.
    assert "alter default privileges revoke execute on functions from public;" in sql


def test_every_callable_function_keeps_an_explicit_revoke():
    """Trigger functions cannot be called directly; every other one revokes PUBLIC itself."""
    head = re.compile(
        r"create\s+or\s+replace\s+function\s+public\.(\w+)\s*\([^)]*\)\s*returns\s+(\w+)", re.I
    )
    names = set()
    for _, raw in sqlscan.load_migrations():
        clean = sqlscan.strip_comments(raw)
        names |= {m.group(1) for m in head.finditer(clean) if m.group(2).lower() != "trigger"}
    all_sql = _norm("\n".join(sqlscan.strip_comments(s) for s in _SQL.values()))
    assert {"credits_grant", "claim_signup_bonus", "user_email_verified"} <= names
    for name in names:
        assert re.search(
            rf"revoke (all|execute) on function public\.{name}\([^)]*\) from public", all_sql
        ), name


def test_service_role_cannot_write_balances_or_truncate_the_ledger():
    sql = _norm(GRANTS)
    assert "revoke truncate on public.credit_ledger from service_role;" in sql
    assert "revoke insert on public.credit_ledger from service_role;" in sql
    assert (
        "revoke insert, update, delete, truncate on public.credit_balances, "
        "public.credit_reservations from service_role;"
    ) in sql


def test_matrix_matches_the_service_role_revokes():
    from tests.rls_matrix import CREDIT_TABLES, SERVICE_ROLE_CREDIT

    assert set(SERVICE_ROLE_CREDIT) == set(CREDIT_TABLES)
    for table, allowed in SERVICE_ROLE_CREDIT.items():
        assert "SELECT" in allowed and "TRUNCATE" not in allowed and "INSERT" not in allowed, table
