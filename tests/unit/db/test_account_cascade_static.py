"""Every user-owned table is deleted with its profile, or anonymised on purpose."""

import re

from tests.unit.db.sqlscan import load_migrations, strip_comments, table_block, tables

SET_NULL = {"credit_ledger", "payment_intents", "llm_calls", "audit_log"}
_CASCADE_REF = re.compile(r"references\s+public\.(\w+)\s*\([^)]*\)\s*on\s+delete\s+cascade", re.I)
_USER_ID_COL = re.compile(r"^\s*user_id\s", re.I | re.M)


def _schema() -> tuple[dict[str, str], str]:
    sql = "\n".join(s for _, s in load_migrations())
    return {t: table_block(sql, t) for t in tables(sql)}, strip_comments(sql)


def _cascade_edges() -> dict[str, set[str]]:
    """parent -> children whose rows go when the parent row goes."""
    blocks, clean = _schema()
    edges: dict[str, set[str]] = {}
    for child, block in blocks.items():
        for parent in _CASCADE_REF.findall(block):
            edges.setdefault(parent, set()).add(child)
    for m in re.finditer(
        r"alter\s+table\s+public\.(\w+)\s+add\s+[^;]*?references\s+public\.(\w+)[^;]*?"
        r"on\s+delete\s+cascade",
        clean,
        re.I | re.S,
    ):
        edges.setdefault(m.group(2), set()).add(m.group(1))
    return edges


def test_every_user_table_reachable_by_cascade():
    blocks, _ = _schema()
    edges = _cascade_edges()
    reached, stack = {"profiles"}, ["profiles"]
    while stack:
        for child in edges.get(stack.pop(), ()):
            if child not in reached:
                reached.add(child)
                stack.append(child)
    owned = {t for t, b in blocks.items() if _USER_ID_COL.search(b)}
    assert owned, "no user-owned tables parsed"
    orphans = owned - reached - SET_NULL
    assert not orphans, f"deleted with the account by nothing: {sorted(orphans)}"


def test_set_null_tables_really_set_null():
    blocks, _ = _schema()
    owner_col = {"audit_log": "actor"}
    for name in SET_NULL:
        col = owner_col.get(name, "user_id")
        line = next(
            (ln for ln in blocks[name].splitlines() if re.match(rf"\s*{col}\s", ln, re.I)), ""
        )
        assert re.search(r"on\s+delete\s+set\s+null", line, re.I), (name, line)
