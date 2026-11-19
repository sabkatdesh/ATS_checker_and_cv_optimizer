import pglast
import pytest

from tests.unit.db import sqlscan

MIGRATIONS = sqlscan.load_migrations()


@pytest.mark.parametrize(("name", "sql"), MIGRATIONS, ids=[n for n, _ in MIGRATIONS])
def test_migration_parses(name, sql):
    assert pglast.parse_sql(sql), name
