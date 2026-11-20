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


TERMINAL = ("succeeded", "failed", "cancelled", "expired", "ineligible")


def _prune() -> str:
    flat = _flat()
    start = flat.index("create or replace function public.prune_checkpoints(")
    return flat[start:]


def test_prune_signature_definer_and_search_path():
    body = _prune()
    assert body.startswith(
        "create or replace function public.prune_checkpoints("
        "p_older interval default interval '7 days') returns int"
    )
    assert "language plpgsql security definer set search_path=''" in body
    assert any("prune_checkpoints" in f for f in sqlscan.definer_functions(_sql()))


def test_prune_deletes_all_three_lg_tables_for_dead_threads():
    body = _prune()
    for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
        assert f"delete from lg.{table} " in body, table  # noqa: S608 - not a query
    # A thread is kept only while its session is live and recently updated.
    assert "s.id::text=" in body
    assert "s.updated_at>=now()-p_older" in body.replace(" ", "")
    for status in TERMINAL:
        assert f"'{status}'" in body
    assert "get diagnostics v_deleted=row_count" in body
    assert body.index("delete from lg.checkpoint_writes") < body.index(
        "delete from lg.checkpoints "
    )


def test_prune_grants():
    body = _prune()
    assert (
        "revoke execute on function public.prune_checkpoints(interval) "
        "from public,anon,authenticated" in body
    )
    assert (
        "grant execute on function public.prune_checkpoints(interval) to app_backend,service_role"
        in body
    )
