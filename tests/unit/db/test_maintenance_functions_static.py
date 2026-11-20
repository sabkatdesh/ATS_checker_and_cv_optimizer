"""Static checks for the maintenance functions migration (claim_signup_bonus)."""

import re

import pglast

from tests.unit.db import sqlscan


def _sql() -> str:
    for name, sql in sqlscan.load_migrations():
        if name.endswith("_maintenance_functions.sql"):
            return sqlscan.strip_comments(sql)
    raise AssertionError("missing maintenance_functions migration")


def _flat() -> str:
    flat = " ".join(_sql().lower().split())
    flat = re.sub(r"\s*([,;=+])\s*", r"\1", flat)
    return re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", flat))


def test_signature_definer_and_search_path():
    flat = _flat()
    assert (
        "create or replace function public.claim_signup_bonus(p_user uuid,p_ip_bucket text,"
        "p_dev_bucket text,p_ip_max int,p_dev_max int,p_amount int) returns text" in flat
    )
    assert "language plpgsql security definer set search_path=''" in flat
    assert any("claim_signup_bonus" in f for f in sqlscan.definer_functions(_sql()))


def test_profile_row_is_locked_first():
    flat = _flat()
    lock = flat.index("from public.profiles where user_id=p_user for update")
    assert lock < flat.index("insert into public.signup_guards")
    assert lock < flat.index("credits_grant(")


def test_guard_rows_are_upserted_and_serialised_per_bucket():
    flat = _flat()
    assert "insert into public.signup_guards (bucket,day,count)" in flat
    assert "on conflict (bucket,day) do update set count=public.signup_guards.count" in flat
    assert "returning count" in flat
    assert "date '1970-01-01'" in flat  # lifetime device bucket sentinel day
    assert "set count=public.signup_guards.count+1" in flat  # bump after the grant


def test_grants_through_credits_grant_with_ledger_key():
    flat = _flat()
    assert (
        "public.credits_grant(p_user,p_amount,'signup_bonus','signup_bonus:' || p_user::text)"
        in flat
    )


def test_outcomes_present():
    flat = _flat()
    for outcome in ("already_granted", "pending_review", "email_not_verified", "granted"):
        assert f"'{outcome}'" in flat
    assert "bonus_review_at=coalesce(bonus_review_at,now())" in flat


def test_execute_is_restricted():
    flat = _flat()
    sig = "public.claim_signup_bonus(uuid,text,text,int,int,int)"
    assert f"revoke execute on function {sig} from public,anon,authenticated;" in flat
    assert f"grant execute on function {sig} to app_backend,service_role;" in flat


def test_function_parses():
    sql = _sql()
    stmts = pglast.parse_sql(sql)
    assert any(type(s.stmt).__name__ == "CreateFunctionStmt" for s in stmts)
    create = sql[: sql.lower().index("revoke execute")]
    assert pglast.parse_plpgsql(create)
