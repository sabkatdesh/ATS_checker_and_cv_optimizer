"""Static checks for the LangGraph checkpoint tables in schema lg (no database)."""

import re

from langgraph.checkpoint.postgres.base import MIGRATIONS as LIB_MIGRATIONS

from tests.unit.db import sqlscan

LG_TABLES = ("checkpoint_migrations", "checkpoints", "checkpoint_blobs", "checkpoint_writes")
CLIENTS = {"public", "anon", "authenticated"}


def _sql() -> str:
    for name, sql in sqlscan.load_migrations():
        if name.endswith("_langgraph_checkpoints.sql"):
            return sqlscan.strip_comments(sql)
    raise AssertionError("missing langgraph_checkpoints migration")


def _norm(sql: str) -> str:
    flat = " ".join(sql.lower().split()).rstrip(";").strip()
    flat = re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", flat))
    return re.sub(r"\s*,\s*", ",", flat)


def _qualified(stmt: str) -> str:
    """The library statement as the migration must spell it: lg-qualified, not concurrent."""
    out = _norm(stmt).replace(" concurrently", "")
    for t in sorted(LG_TABLES, key=len, reverse=True):
        out = re.sub(rf"(?<![\w.]){t}(?=[\s(;]|$)", f"lg.{t}", out)
    return out


def test_pinned_library_has_ten_migrations():
    assert len(LIB_MIGRATIONS) == 10  # bump the migration when the library adds one


def test_ddl_matches_pinned_library_migrations():
    statements = {_norm(s) for s in _sql().split(";") if s.strip()}
    for i, stmt in enumerate(LIB_MIGRATIONS):
        if _norm(stmt) == "select 1":
            continue
        assert _qualified(stmt) in statements, (i, _qualified(stmt))


def test_every_library_version_is_recorded():
    flat = _norm(_sql())
    last = len(LIB_MIGRATIONS) - 1
    assert (
        f"insert into lg.checkpoint_migrations (v) select generate_series(0,{last})"
        " on conflict (v) do nothing" in flat
    )


def test_no_unqualified_checkpoint_tables():
    flat = _norm(_sql())
    for t in LG_TABLES:
        assert not re.search(rf"(?<![\w.]){t}\b(?!_)", flat.replace(f"lg.{t}", "")), t


def test_lg_rls_enabled_without_policies():
    flat = _norm(_sql())
    for t in LG_TABLES:
        assert f"alter table lg.{t} enable row level security" in flat, t
    assert "create policy" not in flat


def test_lg_revoked_from_clients():
    flat = _norm(_sql())
    for t in LG_TABLES:
        m = re.search(rf"revoke all on lg\.{t} from ([^;]+?);", flat + ";")
        assert m, t
        assert {r.strip() for r in m.group(1).split(",")} >= CLIENTS, t
    for g in sqlscan.grants(_sql()):
        grantees = {r.strip(" ;").lower() for r in g.split(" to ")[-1].split(",")}
        assert not grantees & CLIENTS, g


def test_lg_granted_to_app_backend():
    flat = _norm(_sql())
    tables = ",".join(f"lg.{t}" for t in LG_TABLES)
    assert f"grant select,insert,update,delete on {tables} to app_backend" in flat


def test_lint_accepts_lg_tables_only():
    assert not sqlscan.unqualified_create_tables("create table if not exists lg.x (a int);")
    assert sqlscan.unqualified_create_tables("create table other.x (a int);")
