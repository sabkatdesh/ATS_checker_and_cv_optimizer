"""Every foreign-key column in public is the leading column of a non-partial index (or key)."""

import re

from tests.unit.db import sqlscan

ALL_SQL = "\n".join(sqlscan.strip_comments(sql) for _, sql in sqlscan.load_migrations())
_CREATE = re.compile(r"create\s+table\s+public\.(\w+)\s*\((.*?)^\);", re.I | re.S | re.M)
_INLINE_FK = re.compile(r"^\s*(\w+)\s+[\w\s()]*?\breferences\b", re.I | re.M)
_INLINE_PK = re.compile(r"^\s*(\w+)\s+\w+[^,\n]*\bprimary\s+key\b", re.I | re.M)
_TABLE_KEY = re.compile(r"(?:primary\s+key|unique)\s*\(\s*(\w+)", re.I)
_ALTER_FK = re.compile(
    r"alter\s+table\s+public\.(\w+)\s+add\s+constraint\s+\w+\s+foreign\s+key\s*\(\s*(\w+)", re.I
)
_INDEX = re.compile(
    r"create\s+(?:unique\s+)?index\s+(?:if\s+not\s+exists\s+)?\w+\s+on\s+public\.(\w+)"
    r"(?:\s+using\s+\w+)?\s*\(\s*(\w+)[^;]*;",
    re.I | re.S,
)


def fk_columns() -> set[tuple[str, str]]:
    fks = {(m.group(1), m.group(2)) for m in _ALTER_FK.finditer(ALL_SQL)}
    for m in _CREATE.finditer(ALL_SQL):
        fks |= {(m.group(1), c.group(1)) for c in _INLINE_FK.finditer(m.group(2))}
    return fks


def indexed_leading_columns() -> set[tuple[str, str]]:
    covered = set()
    for m in _CREATE.finditer(ALL_SQL):
        body = m.group(2)
        covered |= {(m.group(1), c.group(1)) for c in _INLINE_PK.finditer(body)}
        covered |= {(m.group(1), c.group(1)) for c in _TABLE_KEY.finditer(body)}
    for m in _INDEX.finditer(ALL_SQL):
        if not re.search(r"\)\s*where\b", m.group(0), re.I):  # partial indexes do not count
            covered.add((m.group(1), m.group(2)))
    return covered


def test_scanner_finds_known_foreign_keys():
    fks = fk_columns()
    assert {("cv_sessions", "current_render_id"), ("jobs", "reservation_id")} <= fks
    assert ("audit_log", "actor") in fks and ("photos", "user_id") in fks


def test_partial_index_does_not_cover_a_column():
    assert ("master_profiles", "user_id") in fk_columns()
    assert ALL_SQL.count("master_profiles_one_default_idx") == 1


def test_every_foreign_key_column_is_indexed():
    missing = fk_columns() - indexed_leading_columns()
    assert not missing, sorted(missing)


def test_fk_index_migration_is_idempotent():
    sql = dict(sqlscan.load_migrations())["20261121001300_fk_indexes.sql"]
    stmts = re.findall(r"create\s+index[^;]*;", sqlscan.strip_comments(sql), re.I)
    assert stmts and all("if not exists" in s.lower() for s in stmts)
