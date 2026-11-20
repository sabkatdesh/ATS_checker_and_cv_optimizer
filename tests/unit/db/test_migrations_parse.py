import pglast
import pytest

from tests.unit.db import sqlscan

MIGRATIONS = sqlscan.load_migrations()


@pytest.mark.parametrize(("name", "sql"), MIGRATIONS, ids=[n for n, _ in MIGRATIONS])
def test_migration_parses(name, sql):
    assert pglast.parse_sql(sql), name


def _plpgsql_function_sources():
    """(migration, source text) of every CREATE FUNCTION ... language plpgsql statement."""
    for name, sql in MIGRATIONS:
        for raw in pglast.parse_sql(sql):
            if type(raw.stmt).__name__ != "CreateFunctionStmt":
                continue
            langs = [o for o in raw.stmt.options or () if o.defname == "language"]
            if langs and langs[0].arg.sval == "plpgsql":
                # pglast offsets are UTF-8 byte offsets; stmt_len 0 means "to the end".
                data = sql.encode("utf-8")
                start = raw.stmt_location
                end = start + raw.stmt_len if raw.stmt_len else len(data)
                yield name, data[start:end].decode("utf-8")


FUNCTIONS = list(_plpgsql_function_sources())


def test_plpgsql_functions_were_found():
    assert len(FUNCTIONS) >= 5


@pytest.mark.parametrize(
    ("name", "src"), FUNCTIONS, ids=[f"{n}#{i}" for i, (n, _) in enumerate(FUNCTIONS)]
)
def test_plpgsql_function_bodies_parse(name, src):
    assert pglast.parse_plpgsql(src), name
