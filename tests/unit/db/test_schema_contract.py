import re

import pytest

from tests.unit.db import sqlscan

MIGRATIONS = sqlscan.load_migrations()
ALL_SQL = "\n".join(sql for _, sql in MIGRATIONS)

EXPECTED: dict[str, list[str]] = {
    "profiles": [
        "user_id",
        "display_name",
        "locale",
        "email_verified_at",
        "bonus_granted_at",
        "bonus_review_at",
        "never_paid",
        "preferences",
        "deleted_at",
        "delete_after",
    ],
    "master_profiles": [
        "id",
        "user_id",
        "name",
        "is_default",
        "cv_data",
        "photo_id",
        "domain",
        "completeness",
        "updated_at",
    ],
    "photos": ["id", "user_id", "storage_path", "width", "height", "sha256", "created_at"],
    "cv_sessions": [
        "id",
        "user_id",
        "master_profile_id",
        "source_cv",
        "status",
        "awaiting_kind",
        "pipeline_summary",
        "jd_text",
        "jd_title",
        "jd_company",
        "jd_domain",
        "template_id",
        "template_version",
        "paid_tier",
        "accent",
        "locale",
        "options",
        "score_before",
        "score_after",
        "score_breakdown",
        "tailored_cv",
        "accepted_changes",
        "trust_report",
        "cover_letter_text",
        "current_render_id",
        "price_credits",
        "cost_usd",
        "search_tsv",
        "jd_embedding",
        "created_at",
        "updated_at",
    ],
    "jobs": [
        "id",
        "session_id",
        "user_id",
        "kind",
        "status",
        "stage",
        "attempt",
        "heartbeat_at",
        "cancel_requested_at",
        "expires_at",
        "error_code",
        "reservation_id",
        "idempotency_key",
        "started_at",
        "finished_at",
    ],
    "job_events": ["id", "job_id", "seq", "type", "payload", "created_at"],
    "credit_balances": ["user_id", "balance", "held", "updated_at"],
    "credit_reservations": [
        "id",
        "user_id",
        "session_id",
        "amount",
        "captured",
        "status",
        "created_at",
        "settled_at",
    ],
    "credit_ledger": [
        "id",
        "user_id",
        "kind",
        "delta_balance",
        "delta_held",
        "reservation_id",
        "session_id",
        "idempotency_key",
        "reason",
        "actor",
        "created_at",
    ],
    "idempotency_keys": [
        "user_id",
        "key",
        "route",
        "request_hash",
        "response",
        "status_code",
        "created_at",
    ],
    "renders": [
        "id",
        "session_id",
        "user_id",
        "content_hash",
        "template_id",
        "template_version",
        "pdf_path",
        "pages",
        "thumbnail_path",
        "page_count",
        "render_ms",
        "warnings",
        "created_at",
    ],
    "templates": [
        "id",
        "version",
        "name",
        "tier",
        "ats_safe",
        "columns",
        "photo",
        "recommended_domains",
        "manifest",
        "is_active",
    ],
    "llm_calls": [
        "id",
        "user_id",
        "session_id",
        "job_id",
        "step",
        "provider",
        "model",
        "prompt_version",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "latency_ms",
        "cost_usd",
        "status",
        "error_code",
        "created_at",
    ],
    "feature_flags": ["key", "enabled", "rules"],
    "signup_guards": ["bucket", "day", "count"],
    "payment_intents": [
        "id",
        "user_id",
        "provider",
        "amount_minor",
        "currency",
        "credits",
        "status",
        "provider_ref",
        "idempotency_key",
        "created_at",
        "updated_at",
    ],
    "payment_events": ["id", "provider", "event_id", "payload", "received_at", "processed_at"],
    "audit_log": ["id", "actor", "action", "target", "meta", "created_at"],
}
USER_OWNED = [
    "master_profiles",
    "photos",
    "cv_sessions",
    "jobs",
    "renders",
    "credit_balances",
    "credit_reservations",
    "idempotency_keys",
]
SET_NULL = ["credit_ledger", "payment_intents", "llm_calls"]


def block(table: str) -> str:
    return sqlscan.table_block(ALL_SQL, table)


def col_line(table: str, col: str) -> str:
    for line in block(table).splitlines():
        if re.match(rf"\s+{col}\s", line):
            return line
    return ""


def test_expected_tables_exist():
    created = set(sqlscan.tables(ALL_SQL))
    assert set(EXPECTED) <= created, sorted(set(EXPECTED) - created)


@pytest.mark.parametrize("table", sorted(EXPECTED))
def test_expected_columns(table):
    body = block(table)
    assert body, table
    missing = [c for c in EXPECTED[table] if not re.search(rf"^\s+{c}\s", body, re.M)]
    assert not missing, (table, missing)


@pytest.mark.parametrize("table", USER_OWNED)
def test_user_fks_cascade(table):
    line = col_line(table, "user_id")
    assert "references public.profiles (user_id)" in line, line
    assert "on delete cascade" in line, line


def test_profiles_fk_to_auth_users_cascades():
    line = col_line("profiles", "user_id")
    assert "references auth.users (id) on delete cascade" in line


@pytest.mark.parametrize("table", SET_NULL)
def test_financial_fks_set_null(table):
    line = col_line(table, "user_id")
    assert "on delete set null" in line and "not null" not in line, line


def test_audit_actor_set_null():
    assert "on delete set null" in col_line("audit_log", "actor")


def test_job_events_cascade_from_jobs():
    assert "references public.jobs (id) on delete cascade" in col_line("job_events", "job_id")


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
