"""Static checks for the credit functions and auth hooks migrations."""

import re

from tests.unit.db import sqlscan

SIGNATURES = [
    "public.credits_grant(p_user uuid, p_amount int, p_kind text, p_idem text) returns int",
    "public.credits_reserve(p_user uuid, p_session uuid, p_amount int, p_idem text) returns uuid",
    "public.credits_settle(p_reservation uuid, p_capture int, p_idem text) returns void",
    "public.credits_tier_upgrade(p_user uuid, p_session uuid, p_from text, p_to text,"
    " p_amount int, p_idem text) returns int",
]


def _sql(suffix: str) -> str:
    for name, sql in sqlscan.load_migrations():
        if name.endswith(suffix):
            return sqlscan.strip_comments(sql)
    raise AssertionError(f"missing migration {suffix}")


def _norm(sql: str) -> str:
    return re.sub(r"\s*([(),])\s*", r"\1", " ".join(sql.lower().split()))


def test_credit_function_signatures():
    sql = _norm(_sql("_credit_functions.sql"))
    for sig in SIGNATURES:
        assert _norm("create or replace function " + sig.split(" returns")[0]) in sql, sig
    for sig in SIGNATURES:
        head, ret = sig.split(" returns ")
        assert _norm(f"{head} returns {ret} language plpgsql") in sql, sig


def test_credit_functions_definer_and_revoked():
    sql = _sql("_credit_functions.sql")
    fns = sqlscan.definer_functions(sql)
    assert len(fns) == 4
    flat = " ".join(sql.lower().split())
    for name in ("credits_grant", "credits_reserve", "credits_settle", "credits_tier_upgrade"):
        assert re.search(
            rf"revoke execute on function public\.{name}\([^)]*\)\s+from public, anon, authenticated;",
            flat,
        ), name
        assert re.search(
            rf"grant execute on function public\.{name}\([^)]*\)\s+to app_backend, service_role;",
            flat,
        ), name


def test_credit_functions_idempotent_ledger_and_lock():
    sql = " ".join(_sql("_credit_functions.sql").lower().split())
    assert sql.count("on conflict (idempotency_key) do nothing") >= 3
    for code in ("insufficient_credits", "invalid_amount", "reservation_settled"):
        assert code in sql
    assert "for update" in sql
    assert "errcode = 'p0001'" in sql


def test_credit_functions_schema_qualified():
    sql = _sql("_credit_functions.sql")
    assert not re.search(r"\b(?:from|into|update|join)\s+(?!public\.)credit_", sql, re.I)


def test_auth_triggers_present():
    sql = " ".join(_sql("_auth_hooks.sql").lower().split())
    assert "after insert on auth.users" in sql
    assert "after update of email_confirmed_at on auth.users" in sql
    assert "execute function public.handle_new_user()" in sql
    assert "execute function public.handle_user_verified()" in sql
    assert re.search(r"insert into public\.profiles \(user_id, email_verified_at\)", sql)
    assert re.search(r"insert into public\.credit_balances", sql)


def test_user_email_verified_backend_only():
    sql = " ".join(_sql("_auth_hooks.sql").lower().split())
    assert "grant execute on function public.user_email_verified(uuid) to app_backend;" in sql
    assert "service_role" not in sql.split("user_email_verified(uuid) to")[1].split(";")[0]
    assert (
        "revoke execute on function public.user_email_verified(uuid) from public, anon, authenticated"
        in sql
    )
    assert len(sqlscan.definer_functions(_sql("_auth_hooks.sql"))) == 3


def _fn(name: str) -> str:
    sql = " ".join(_sql("_credit_functions.sql").lower().split())
    start = sql.index(f"create or replace function public.{name}(")
    nxt = sql.find("create or replace function", start + 10)
    return sql[start : nxt if nxt != -1 else len(sql)]


FUNCS = ("credits_grant", "credits_reserve", "credits_settle", "credits_tier_upgrade")


def test_null_key_guard_in_all_functions():
    for name in FUNCS:
        body = _fn(name)
        assert "if p_idem is null or btrim(p_idem) = '' then" in body, name
        assert "'invalid_idempotency_key'" in body.lower(), name


def test_null_argument_guards():
    assert "p_user is null" in _fn("credits_grant")
    for name in ("credits_reserve", "credits_tier_upgrade"):
        assert "p_user is null" in _fn(name) and "p_session is null" in _fn(name), name
    assert "p_reservation is null" in _fn("credits_settle")
    assert "'invalid_kind'" in _fn("credits_grant")


def test_replay_verifies_same_operation():
    assert "v_old_kind is distinct from p_kind" in _fn("credits_grant")
    assert "v_old_kind is distinct from 'reserve'" in _fn("credits_reserve")
    assert "v_old_kind is distinct from 'tier_upgrade'" in _fn("credits_tier_upgrade")
    for name in ("credits_grant", "credits_reserve", "credits_tier_upgrade"):
        assert "v_old_user is distinct from p_user" in _fn(name), name
        assert "'idempotency_mismatch'" in _fn(name), name


def test_settle_inserts_do_not_swallow_conflicts():
    body = _fn("credits_settle")
    assert "on conflict" not in body
    assert "if p_capture > 0 then" in body
    assert "if v_amount - p_capture > 0 then" in body
    assert body.count("for update") == 2
    assert "'reservation_not_found'" in body
