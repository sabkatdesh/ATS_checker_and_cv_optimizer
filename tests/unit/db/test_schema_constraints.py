"""Schema constraints, status enums, the ledger trigger, the template seed and RLS placement."""

import re

from tests.unit.db import sqlscan
from tests.unit.db.test_schema_contract import ALL_SQL, MIGRATIONS, block, col_line


def test_checks_and_uniques():
    assert "char_length(jd_text) <= 15000" in block("cv_sessions")
    assert "held <= balance" in block("credit_balances")
    assert "balance >= 0" in block("credit_balances")
    assert "held >= 0" in block("credit_balances")
    assert "unique (user_id, idempotency_key)" in block("jobs")
    assert "unique" in col_line("credit_ledger", "idempotency_key")
    assert "unique" in col_line("renders", "content_hash")
    assert re.search(
        r"unique index \w+\s+on public\.master_profiles \(user_id\) where is_default", ALL_SQL
    )
    assert "extensions.vector(512)" in col_line("cv_sessions", "jd_embedding")
    assert "generated always as" in block("cv_sessions")


def test_status_enums_complete():
    for v in (
        "draft",
        "queued",
        "running",
        "awaiting_input",
        "succeeded",
        "failed",
        "cancelled",
        "expired",
        "ineligible",
    ):
        assert f"'{v}'" in block("cv_sessions")
    for v in (
        "queued",
        "running",
        "awaiting_input",
        "cancelling",
        "succeeded",
        "failed",
        "cancelled",
        "expired",
    ):
        assert f"'{v}'" in block("jobs")


def test_ledger_has_append_only_trigger():
    clean = sqlscan.strip_comments(ALL_SQL)
    assert re.search(r"before\s+update\s+or\s+delete\s+on\s+public\.credit_ledger", clean, re.I)
    assert "credit_ledger_append_only" in clean
    fn = re.search(r"function public\.credit_ledger_append_only\(\).*?\$\$;", clean, re.I | re.S)
    assert fn
    assert "set search_path = ''" in fn.group(0)
    assert "LEDGER_IMMUTABLE" in fn.group(0) and "P0001" in fn.group(0)
    assert "new.user_id is null" in fn.group(0) and "old.user_id is not null" in fn.group(0)


def test_templates_seed_has_six_rows_upsert():
    seed = sqlscan.strip_comments(
        next((sql for n, sql in MIGRATIONS if n.endswith("_seed_templates.sql")), "")
    )
    assert "on conflict (id) do update" in seed
    for tid in ("classic", "modern", "compact", "academic", "trades", "creative"):
        assert f"('{tid}', 1," in seed
    assert len(re.findall(r"^\s+\('\w+', 1,", seed, re.M)) == 6


def test_rls_enabled_in_creating_file():
    for name, sql in MIGRATIONS:
        assert set(sqlscan.tables(sql)) <= sqlscan.rls_enabled_tables(sql), name
