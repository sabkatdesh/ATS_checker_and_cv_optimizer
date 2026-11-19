import re

from tests.rls_matrix import CREDIT_TABLES, MATRIX
from tests.unit.db import sqlscan

MIGRATIONS = sqlscan.load_migrations()
ALL_SQL = sqlscan.strip_comments("\n".join(s for _, s in MIGRATIONS))
POLICY = re.compile(
    r"create policy (?P<name>\S+) on public\.(?P<table>\w+) for (?P<cmd>\w+) "
    r"to (?P<roles>[\w, ]+?) using \((?P<using>.*)\);$",
    re.I,
)
OWN = "user_id = (select auth.uid())"


def _parsed():
    out = {}
    for _, sql in MIGRATIONS:
        for p in sqlscan.policies(sql):
            m = POLICY.match(p)
            assert m, p
            out.setdefault(m["table"], []).append(m)
    return out


def _access(table, role):
    for m in _parsed().get(table, []):
        roles = {r.strip().lower() for r in m["roles"].split(",")}
        if role not in roles:
            continue
        using = m["using"].strip()
        if using == "is_active":
            return "select_active"
        return "select_own"
    return "none"


def test_matrix_covers_every_table():
    created = {t for _, sql in MIGRATIONS for t in sqlscan.tables(sql)}
    assert created == set(MATRIX)


def test_rls_matrix_matches_spec():
    for table, rule in MATRIX.items():
        assert _access(table, "anon") == rule.anon, table
        assert _access(table, "authenticated") == rule.authenticated, table


def test_all_policies_are_select_only():
    for table, ms in _parsed().items():
        assert all(m["cmd"].lower() == "select" for m in ms), table


def test_own_policies_use_user_id():
    for table, rule in MATRIX.items():
        if rule.authenticated != "select_own" or table == "job_events":
            continue
        (m,) = _parsed()[table]
        assert m["using"].strip() == OWN, table


def test_job_events_policy_via_jobs():
    (m,) = _parsed()["job_events"]
    u = " ".join(m["using"].split())
    assert u == (
        "exists (select 1 from public.jobs j where j.id = job_id "
        "and j.user_id = (select auth.uid()))"
    )


def test_auth_uid_wrapped_in_select():
    for _, sql in MIGRATIONS:
        clean = sqlscan.strip_comments(sql)
        total = len(re.findall(r"auth\.uid\(\)", clean))
        wrapped = len(re.findall(r"\(\s*select\s+auth\.uid\(\)\s*\)", clean))
        assert total == wrapped


def _backend_grants():
    res = {}
    for g in sqlscan.grants(ALL_SQL):
        m = re.fullmatch(r"grant ([a-z, ]+) on (?:table )?public\.(\w+) to app_backend;", g, re.I)
        if m:
            privs = {p.strip().lower() for p in m[1].split(",")}
            res.setdefault(m[2], set()).update(privs)
    return res


def test_backend_grants_match_matrix():
    got = _backend_grants()
    for table, rule in MATRIX.items():
        want = {"select"} if rule.backend == "select" else {"select", "insert", "update", "delete"}
        assert got.get(table) == want, table


def test_credit_tables_not_writable_by_backend():
    assert not re.search(
        r"grant\s+[^;]*\b(insert|update|delete|truncate|all)\b[^;]*on\s+(table\s+)?"
        r"public\.credit_\w+[^;]*\bto\b[^;]*app_backend",
        ALL_SQL,
        re.I,
    )


def test_client_grants_are_select_only_on_readable_tables():
    for g in sqlscan.grants(ALL_SQL):
        if re.search(r"\bto\b[^;]*\b(anon|authenticated)\b", g, re.I):
            m = re.fullmatch(r"grant select on (?:table )?public\.(\w+) to ([\w, ]+);", g, re.I)
            assert m, g
            roles = {r.strip() for r in m[2].split(",")}
            rule = MATRIX[m[1]]
            assert ("anon" in roles) <= (rule.anon != "none"), g
            assert rule.authenticated != "none", g


def test_every_readable_table_is_granted_to_authenticated():
    granted = {
        m[1]
        for g in sqlscan.grants(ALL_SQL)
        if (m := re.fullmatch(r"grant select on (?:table )?public\.(\w+) to ([\w, ]+);", g, re.I))
        and "authenticated" in m[2]
    }
    assert granted == {t for t, r in MATRIX.items() if r.authenticated != "none"}


def test_client_roles_revoked_then_default_privileges_locked():
    assert re.search(
        r"revoke all on all tables in schema public from anon, authenticated;", ALL_SQL, re.I
    )
    assert re.search(
        r"alter default privileges[^;]*in schema public[^;]*revoke all on tables "
        r"from anon, authenticated;",
        ALL_SQL,
        re.I,
    )


def test_ledger_truncate_revoked_and_credit_tables_closed_to_clients():
    assert re.search(
        r"revoke truncate on public\.credit_ledger from public, anon, authenticated, app_backend;",
        ALL_SQL,
        re.I,
    )
    for t in CREDIT_TABLES:
        assert re.search(
            rf"revoke all on public\.{t} from public, anon, authenticated;", ALL_SQL, re.I
        ), t


def test_no_lg_grants_to_client_roles():
    for g in sqlscan.grants(ALL_SQL):
        if re.search(r"\blg\b", g):
            assert not re.search(r"\b(anon|authenticated|public)\b", g.split(" to ")[-1], re.I), g


def test_backend_has_sequence_privileges():
    assert re.search(
        r"grant usage, select on all sequences in schema public to app_backend;", ALL_SQL, re.I
    )
    assert re.search(
        r"alter default privileges in schema public grant usage, select on sequences "
        r"to app_backend;",
        ALL_SQL,
        re.I,
    )
    serial = [
        t
        for _, sql in MIGRATIONS
        for t in sqlscan.tables(sql)
        if re.search(
            r"bigserial|generated\s+\w+\s+as\s+identity", sqlscan.table_block(sql, t), re.I
        )
    ]
    assert serial, "expected tables with serial/identity ids"


def test_client_roles_revoked_from_existing_sequences_and_functions():
    assert re.search(
        r"revoke all on all sequences in schema public from anon, authenticated;", ALL_SQL, re.I
    )
    assert re.search(
        r"revoke all on all functions in schema public from public, anon, authenticated;",
        ALL_SQL,
        re.I,
    )
