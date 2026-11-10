from unittest.mock import MagicMock

from app.adapters.db.supabase_legacy_store import SupabaseLegacyStore

COLUMNS = (
    "thread_id, status, job_description, "
    "ats_score, semantic_score, improvement_score, eligibility_score, "
    "pdf_url, template_id, domain, cover_letter_requested, "
    "cover_letter_text, cover_letter_pdf_url, created_at"
)


def _store() -> tuple[SupabaseLegacyStore, MagicMock]:
    client = MagicMock()
    return SupabaseLegacyStore(client), client


def test_get_cv_profile_query():
    store, client = _store()
    chain = client.table.return_value.select.return_value.eq.return_value.single.return_value
    chain.execute.return_value.data = {"user_id": "u1"}
    assert store.get_cv_profile("u1") == {"user_id": "u1"}
    client.table.assert_called_once_with("cv_profiles")
    client.table.return_value.select.assert_called_once_with("*")
    client.table.return_value.select.return_value.eq.assert_called_once_with("user_id", "u1")


def test_get_cv_profile_swallows_errors_returns_none():
    store, client = _store()
    client.table.side_effect = RuntimeError("boom")
    assert store.get_cv_profile("u1") is None


def test_save_cv_profile_upserts_on_user_id():
    store, client = _store()
    upsert = client.table.return_value.upsert
    upsert.return_value.execute.return_value.data = [{"ok": 1}]
    assert store.save_cv_profile("u1", {"a": 1}) == [{"ok": 1}]
    client.table.assert_called_once_with("cv_profiles")
    upsert.assert_called_once_with({"a": 1, "user_id": "u1"}, on_conflict="user_id")


def test_create_session_payload_omits_empty_optionals():
    store, client = _store()
    insert = client.table.return_value.insert
    insert.return_value.execute.return_value.data = [{"thread_id": "t"}]
    assert store.create_session("u1", "t", "jd") == {"thread_id": "t"}
    client.table.assert_called_once_with("cv_sessions")
    insert.assert_called_once_with(
        {
            "user_id": "u1",
            "thread_id": "t",
            "job_description": "jd",
            "status": "running",
            "template_id": "classic",
            "cover_letter_requested": False,
        }
    )


def test_create_session_includes_optionals_when_given():
    store, client = _store()
    insert = client.table.return_value.insert
    insert.return_value.execute.return_value.data = []
    assert store.create_session("u", "t", "jd", domain="tech", cover_letter_tone="formal") is None
    payload = insert.call_args.args[0]
    assert payload["domain"] == "tech"
    assert payload["cover_letter_tone"] == "formal"
    assert "cover_letter_length" not in payload


def test_get_user_sessions_select_columns():
    store, client = _store()
    chain = client.table.return_value.select.return_value.eq.return_value.order.return_value
    chain.execute.return_value.data = None
    assert store.get_user_sessions("u1") == []
    client.table.assert_called_once_with("cv_sessions")
    client.table.return_value.select.assert_called_once_with(COLUMNS)
    client.table.return_value.select.return_value.eq.assert_called_once_with("user_id", "u1")
    client.table.return_value.select.return_value.eq.return_value.order.assert_called_once_with(
        "created_at", desc=True
    )


def test_update_session_query():
    store, client = _store()
    store.update_session("t", {"status": "done"})
    client.table.assert_called_once_with("cv_sessions")
    client.table.return_value.update.assert_called_once_with({"status": "done"})
    client.table.return_value.update.return_value.eq.assert_called_once_with("thread_id", "t")


def test_upload_pdf_path_and_public_url(tmp_path):
    store, client = _store()
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF")
    bucket = client.storage.from_.return_value
    bucket.get_public_url.return_value = "https://x/pdf"
    assert store.upload_pdf_to_storage("t1", "u1", str(pdf)) == "https://x/pdf"
    client.storage.from_.assert_called_with("cv-pdfs")
    args = bucket.upload.call_args.args
    assert args[0] == "pdfs/u1/t1.pdf"
    assert args[2] == {"content-type": "application/pdf", "upsert": "true"}
    bucket.get_public_url.assert_called_once_with("pdfs/u1/t1.pdf")


def test_get_coin_balance_defaults_zero_on_error():
    store, client = _store()
    client.table.side_effect = RuntimeError("down")
    assert store.get_coin_balance("u1") == 0


def test_get_coin_balance_reads_balance():
    store, client = _store()
    chain = client.table.return_value.select.return_value.eq.return_value.single.return_value
    chain.execute.return_value.data = {"balance": 7}
    assert store.get_coin_balance("u1") == 7
    client.table.return_value.select.assert_called_once_with("balance")


def _with_balance(store: SupabaseLegacyStore, balance: int) -> None:
    store.get_coin_balance = lambda user_id: balance  # type: ignore[method-assign]


def test_deduct_coins_insufficient_returns_false_no_writes():
    store, client = _store()
    _with_balance(store, 1)
    assert store.deduct_coins("u1", 5, "d") is False
    client.table.assert_not_called()


def test_deduct_coins_writes_balance_and_transaction():
    store, client = _store()
    _with_balance(store, 10)
    assert store.deduct_coins("u1", 4, "d") is True
    tbl = client.table.return_value
    tbl.update.assert_called_once_with({"balance": 6})
    tbl.insert.assert_called_once_with(
        {"user_id": "u1", "amount": -4, "type": "charge", "description": "d"}
    )


def test_add_coins_writes_balance_and_transaction():
    store, client = _store()
    _with_balance(store, 3)
    store.add_coins("u1", 5, "buy")
    tbl = client.table.return_value
    tbl.upsert.assert_called_once_with({"user_id": "u1", "balance": 8}, on_conflict="user_id")
    tbl.insert.assert_called_once_with(
        {"user_id": "u1", "amount": 5, "type": "purchase", "description": "buy"}
    )


def test_get_coin_transactions_query():
    store, client = _store()
    chain = client.table.return_value.select.return_value.eq.return_value.order.return_value
    chain.execute.return_value.data = [{"id": 1}]
    assert store.get_coin_transactions("u1") == [{"id": 1}]
    client.table.assert_called_once_with("coin_transactions")
    client.table.return_value.select.return_value.eq.return_value.order.assert_called_once_with(
        "created_at", desc=True
    )
