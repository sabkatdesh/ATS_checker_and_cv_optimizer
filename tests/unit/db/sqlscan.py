"""Offline regex helpers for linting the Supabase migration SQL."""

import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "supabase" / "migrations"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"--[^\n]*")
_IDENT = r'"?(\w+)"?'
_TABLE = re.compile(rf"create\s+table\s+(?:if\s+not\s+exists\s+)?public\.{_IDENT}", re.I)
# The private lg schema holds only the LangGraph checkpoint tables.
_LG_TABLE = re.compile(rf"create\s+table\s+(?:if\s+not\s+exists\s+)?lg\.{_IDENT}", re.I)
_POLICY = re.compile(r"create\s+policy\s+.+?;", re.I | re.S)
_FUNCTION = re.compile(
    r"create\s+(?:or\s+replace\s+)?function\s+.+?(?=create\s+(?:or\s+replace\s+)?function\s|\Z)",
    re.I | re.S,
)


def strip_comments(sql: str) -> str:
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", sql))


def load_migrations() -> list[tuple[str, str]]:
    """Return (name, sql) for every migration file, sorted by name."""
    if not MIGRATIONS_DIR.is_dir():
        return []
    return [(p.name, p.read_text(encoding="utf-8")) for p in sorted(MIGRATIONS_DIR.glob("*.sql"))]


def tables(sql: str) -> list[str]:
    """Names of tables created in the public schema."""
    return [m.group(1) for m in _TABLE.finditer(strip_comments(sql))]


def rls_enabled_tables(sql: str) -> set[str]:
    pat = re.compile(
        rf"alter\s+table\s+(?:only\s+)?public\.{_IDENT}\s+enable\s+row\s+level\s+security",
        re.I,
    )
    return {m.group(1) for m in pat.finditer(strip_comments(sql))}


def policies(sql: str) -> list[str]:
    """Full text of each create policy statement, whitespace-normalised."""
    return [" ".join(m.group(0).split()) for m in _POLICY.finditer(strip_comments(sql))]


def definer_functions(sql: str) -> list[str]:
    """Text of each function definition that declares security definer."""
    clean = strip_comments(sql)
    return [
        m.group(0)
        for m in _FUNCTION.finditer(clean)
        if re.search(r"security\s+definer", m.group(0), re.I)
    ]


def unqualified_create_tables(sql: str) -> list[str]:
    """create table statements that are not plain `public.<name>` or `lg.<name>` (lint bypass)."""
    clean = strip_comments(sql)
    stmts = re.findall(r"create\s+(?:\w+\s+)*?table\s+[^\n(]*", clean, re.I)
    return [s for s in stmts if not (_TABLE.match(s) or _LG_TABLE.match(s))]


def table_block(sql: str, name: str) -> str:
    """Body of `create table public.<name> ( ... );` (closing paren at line start)."""
    m = re.search(
        rf"create\s+table\s+public\.{name}\s*\(.*?^\);", strip_comments(sql), re.I | re.S | re.M
    )
    return m.group(0) if m else ""


def grants(sql: str) -> list[str]:
    return [
        " ".join(m.group(0).split())
        for m in re.finditer(r"grant\s+.+?;", strip_comments(sql), re.I | re.S)
    ]
