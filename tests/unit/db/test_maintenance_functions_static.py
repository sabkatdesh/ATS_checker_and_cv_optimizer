"""Static checks for the maintenance functions migration (guard_bump)."""

import re

from tests.unit.db import sqlscan


def _sql() -> str:
    for name, sql in sqlscan.load_migrations():
        if name.endswith("_maintenance_functions.sql"):
            return sqlscan.strip_comments(sql)
    raise AssertionError("missing maintenance_functions migration")


def _flat() -> str:
    """Lowercase, whitespace removed around punctuation, so assertions ignore layout."""
    flat = " ".join(_sql().lower().split())
    flat = re.sub(r"\s*([,;=+])\s*", r"\1", flat)
    return re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", flat))


def test_guard_bump_signature_and_definer():
    flat = _flat()
    assert "create or replace function public.guard_bump(p_buckets text[],p_day date)" in flat
    assert "returns void language plpgsql security definer set search_path=''" in flat
    assert any("guard_bump" in f for f in sqlscan.definer_functions(_sql()))


def test_guard_bump_upserts_count_plus_one_on_pk():
    flat = _flat()
    assert "insert into public.signup_guards (bucket,day,count)" in flat
    assert "on conflict (bucket,day) do update set count=public.signup_guards.count+1" in flat
    assert "unnest(p_buckets)" in flat


def test_guard_bump_execute_is_restricted():
    flat = _flat()
    assert (
        "revoke execute on function public.guard_bump(text[],date) "
        "from public,anon,authenticated;" in flat
    )
    assert (
        "grant execute on function public.guard_bump(text[],date) to app_backend,service_role;"
        in flat
    )
