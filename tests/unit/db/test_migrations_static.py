import re

from tests.unit.db import sqlscan

MIGRATIONS = sqlscan.load_migrations()
NAME = re.compile(r"^\d{14}_[a-z0-9_]+\.sql$")
WRITE_POLICY = re.compile(r"for\s+(insert|update|delete|all)\b", re.I)
CLIENT_ROLE = re.compile(r"\bto\b[^;]*\b(anon|authenticated)\b", re.I)


def test_migrations_exist():
    assert MIGRATIONS, "supabase/migrations has no files"


def test_names_are_cli_timestamps():
    names = [n for n, _ in MIGRATIONS]
    assert all(NAME.match(n) for n in names), names
    stamps = [n[:14] for n in names]
    assert stamps == sorted(set(stamps)), "timestamps must be strictly increasing"


def test_each_file_under_300_lines():
    for name, sql in MIGRATIONS:
        assert len(sql.splitlines()) < 300, name


def test_no_for_all_policies():
    for name, sql in MIGRATIONS:
        for p in sqlscan.policies(sql):
            assert not re.search(r"for\s+all\b", p, re.I), (name, p)


def test_every_public_table_enables_rls():
    created = {t for _, sql in MIGRATIONS for t in sqlscan.tables(sql)}
    enabled = {t for _, sql in MIGRATIONS for t in sqlscan.rls_enabled_tables(sql)}
    assert created <= enabled, sorted(created - enabled)


def test_no_client_write_policies():
    for name, sql in MIGRATIONS:
        for p in sqlscan.policies(sql):
            assert not (WRITE_POLICY.search(p) and CLIENT_ROLE.search(p)), (name, p)


def test_definer_functions_pin_search_path():
    for name, sql in MIGRATIONS:
        for fn in sqlscan.definer_functions(sql):
            assert re.search(r"set\s+search_path\s*=\s*''", fn, re.I), (name, fn[:80])


def test_no_grants_to_anon_except_templates_select():
    for name, sql in MIGRATIONS:
        for g in sqlscan.grants(sql):
            if re.search(r"\bto\b[^;]*\banon\b", g, re.I):
                assert re.fullmatch(r"grant select on (table )?public\.templates to .*", g, re.I), (
                    name,
                    g,
                )


def test_legacy_dir_not_applied():
    assert not [n for n, _ in MIGRATIONS if n.startswith("000_")]


def test_sqlscan_ignores_comments():
    sql = "-- create table public.a (x int);\n/* create policy p on t for all to anon; */\ncreate table public.b (x int);"
    assert sqlscan.tables(sql) == ["b"]
    assert sqlscan.policies(sql) == []
