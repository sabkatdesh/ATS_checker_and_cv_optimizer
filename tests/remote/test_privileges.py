"""Effective ACLs from pg_catalog (readable by any role), not from information_schema (which
only shows grants involving the current role).

This also covers default privileges: whatever pg_default_acl would have granted at CREATE
time (for postgres or supabase_admin alike) shows up in relacl/proacl, so asserting the
effective ACLs is the real check. The pg_default_acl test then guards future objects.
"""

from tests.remote._helpers import Conn, scalar
from tests.rls_matrix import MATRIX, SERVICE_ROLE_CREDIT

CLIENTS = ("anon", "authenticated")

_ACL = """
select c.relname::text as name, r.rolname::text as grantee, a.privilege_type as priv
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
cross join lateral aclexplode(
  coalesce(c.relacl, acldefault(%(kind)s::text::"char", c.relowner))) a
left join pg_roles r on r.oid = a.grantee
where n.nspname = %(schema)s::text and c.relkind::text = any(%(relkinds)s::text[])
"""
# A NULL relacl/proacl means "built-in defaults", so acldefault() stands in for it. Note that
# PostgreSQL's built-in default for functions grants EXECUTE to PUBLIC and cannot be revoked
# per schema; that is why every migration revokes EXECUTE function by function, and why the
# function test below checks effective ACLs rather than pg_default_acl alone.
_FN_ACL = """
select p.oid::regprocedure::text as name, coalesce(r.rolname, 'PUBLIC') as grantee,
       a.privilege_type as priv
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
left join pg_roles r on r.oid = a.grantee
where n.nspname = 'public'
"""


def _grants(conn: Conn, schema: str, kind: str, relkinds: list[str]) -> set[tuple[str, str, str]]:
    params = {"schema": schema, "kind": kind, "relkinds": relkinds}
    return {
        (r["name"], r["grantee"] or "PUBLIC", r["priv"])
        for r in conn.execute(_ACL, params).fetchall()
    }


def test_public_tables_are_exactly_the_matrix(backend_conn: Conn) -> None:
    sql = "select array_agg(tablename::text) from pg_tables where schemaname = 'public'"
    assert set(scalar(backend_conn, sql) or []) == set(MATRIX)


def test_client_table_grants_match_matrix(backend_conn: Conn) -> None:
    grants = _grants(backend_conn, "public", "r", ["r", "p", "v", "m", "f"])
    actual = {g for g in grants if g[1] in (*CLIENTS, "PUBLIC")}
    expected = {
        (table, role, "SELECT")
        for table, rule in MATRIX.items()
        for role, access in (("anon", rule.anon), ("authenticated", rule.authenticated))
        if access != "none"
    }
    assert actual == expected


def test_clients_have_no_sequence_privileges(backend_conn: Conn) -> None:
    grants = _grants(backend_conn, "public", "s", ["S"])
    assert {g for g in grants if g[1] in (*CLIENTS, "PUBLIC")} == set()


def test_clients_cannot_execute_any_public_function(backend_conn: Conn) -> None:
    rows = backend_conn.execute(_FN_ACL).fetchall()
    leaked = {(r["name"], r["grantee"]) for r in rows if r["grantee"] in (*CLIENTS, "PUBLIC")}
    assert leaked == set()


def test_default_privileges_grant_clients_nothing(backend_conn: Conn) -> None:
    """For every role that owns objects in public, its default ACLs (schema-level and global)
    must not hand anon/authenticated/PUBLIC anything on future tables, sequences or functions."""
    sql = """
    with owners as (
      select c.relowner as oid from pg_class c join pg_namespace n on n.oid = c.relnamespace
      where n.nspname = 'public'
      union
      select p.proowner from pg_proc p join pg_namespace n on n.oid = p.pronamespace
      where n.nspname = 'public'
    )
    select o.rolname as owner, d.defaclobjtype::text as objtype,
           coalesce(g.rolname, 'PUBLIC') as grantee, a.privilege_type as priv
    from pg_default_acl d
    join pg_roles o on o.oid = d.defaclrole
    cross join lateral aclexplode(d.defaclacl) a
    left join pg_roles g on g.oid = a.grantee
    where d.defaclrole in (select oid from owners)
      and (d.defaclnamespace = 0 or d.defaclnamespace = 'public'::regnamespace)
    """
    rows = backend_conn.execute(sql).fetchall()
    leaked = {
        (r["owner"], r["objtype"], r["grantee"], r["priv"])
        for r in rows
        if r["grantee"] in (*CLIENTS, "PUBLIC")
    }
    assert leaked == set()


def test_backend_has_schema_and_sequence_usage(backend_conn: Conn) -> None:
    for schema in ("public", "lg"):
        sql = "select has_schema_privilege('app_backend', %s, 'USAGE')"
        assert scalar(backend_conn, sql, (schema,)) is True, schema
    seqs = backend_conn.execute(
        "select sequencename from pg_sequences where schemaname = 'public'"
    ).fetchall()
    assert seqs, "expected bigserial sequences in public"
    for r in seqs:
        name = f"public.{r['sequencename']}"
        sql = "select has_sequence_privilege('app_backend', %s, 'USAGE')"
        assert scalar(backend_conn, sql, (name,)) is True, name


def test_lg_is_backend_only(backend_conn: Conn) -> None:
    for role in CLIENTS:
        sql = "select has_schema_privilege(%s, 'lg', 'USAGE')"
        assert scalar(backend_conn, sql, (role,)) is False, role
    for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"):
        for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            sql = "select has_table_privilege('app_backend', %s, %s)"
            assert scalar(backend_conn, sql, (f"lg.{table}", priv)) is True, (table, priv)
        grants = _grants(backend_conn, "lg", "r", ["r"])
        assert not {g for g in grants if g[0] == table and g[1] in (*CLIENTS, "PUBLIC")}


def test_backend_credit_tables_are_select_only(backend_conn: Conn) -> None:
    for table in ("credit_balances", "credit_ledger", "credit_reservations"):
        for priv, expected in (
            ("SELECT", True),
            ("INSERT", False),
            ("UPDATE", False),
            ("DELETE", False),
            ("TRUNCATE", False),
        ):
            sql = "select has_table_privilege('app_backend', %s, %s)"
            assert scalar(backend_conn, sql, (f"public.{table}", priv)) is expected, (table, priv)


def test_service_role_credit_privileges_are_minimal(backend_conn: Conn) -> None:
    for table, allowed in SERVICE_ROLE_CREDIT.items():
        for priv in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
            sql = "select has_table_privilege('service_role', %s, %s)"
            got = scalar(backend_conn, sql, (f"public.{table}", priv))
            assert got is (priv in allowed), (table, priv)
