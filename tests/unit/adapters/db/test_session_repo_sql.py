from datetime import UTC, datetime

import psycopg
import pytest

from app.adapters.db.credit_repo import PgCreditRepo
from app.adapters.db.errors import DbConflict
from app.adapters.db.render_repo import PgRenderRepo
from app.adapters.db.session_repo import PgSessionRepo
from app.domain.common import uuid7
from app.ports.repositories import COVER_LETTER_RENDER
from tests.fakes.recording_pool import RecordingPool, assert_user_scoped

UID = "11111111-1111-1111-1111-111111111111"
SID = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"


def _session_calls(pool: RecordingPool) -> None:
    repo = PgSessionRepo(pool)
    repo.create(UID, SID, jd_text="jd", source_cv={"a": 1}, options={}, template_id="classic")
    repo.get(UID, SID)
    repo.list_for_user(UID)
    repo.update(UID, SID, status="running", awaiting_kind=None)
    renders = RecordingPool(rows=[{"id": "r1"}])
    PgRenderRepo(renders).add(
        UID, SID, pdf_path=f"{UID}/{SID}/cv.pdf", content_hash="h", template_id="classic"
    )
    pool.log.extend(renders.log)
    credits = PgCreditRepo(pool)
    credits.balance(UID)
    credits.ledger(UID)


def test_session_queries_scope_by_user():
    pool = RecordingPool()
    _session_calls(pool)
    assert len(pool.log) == 7
    for sql, params in pool.log:
        assert_user_scoped(sql)
        assert params["user_id"] == UID


def test_session_reads_join_renders_of_the_same_user():
    pool = RecordingPool()
    PgSessionRepo(pool).get(UID, SID)
    sql = pool.log[0][0]
    assert "r.user_id = s.user_id" in sql
    assert "r.session_id = s.id" in sql
    assert "c.user_id = s.user_id" in sql
    assert "s.id = %(session_id)s" in sql
    assert f"c.template_id = '{COVER_LETTER_RENDER}'" in sql


@pytest.mark.parametrize("bad", ["nope", "", "thread_abc", f"{SID}x", SID.replace("-", "")])
def test_get_malformed_id_is_none_without_a_query(bad):
    pool = RecordingPool(rows=[{"id": SID}])
    repo = PgSessionRepo(pool)
    assert repo.get(UID, bad) is None
    repo.update(UID, bad, status="failed")
    assert pool.log == []


def test_create_rejects_a_malformed_id():
    with pytest.raises(ValueError):
        PgSessionRepo(RecordingPool()).create(
            UID, "thread_x", jd_text="jd", source_cv={}, options={}, template_id="classic"
        )


def test_create_inserts_a_running_row_with_json_payloads():
    pool = RecordingPool()
    PgSessionRepo(pool).create(
        UID, SID, jd_text="jd", source_cv={"a": 1}, options={"cover_letter": True}, template_id="t"
    )
    sql, params = pool.log[0]
    assert "'running'" in sql
    assert params["source_cv"].obj == {"a": 1}
    assert params["options"].obj == {"cover_letter": True}


def test_update_rejects_unknown_column():
    pool = RecordingPool()
    with pytest.raises(ValueError, match="pdf_url"):
        PgSessionRepo(pool).update(UID, SID, status="running", pdf_url="x")
    with pytest.raises(ValueError):
        PgSessionRepo(pool).update(UID, SID, **{"status = 'x'; --": 1})
    assert pool.log == []


def test_update_wraps_json_columns_and_skips_empty():
    pool = RecordingPool()
    repo = PgSessionRepo(pool)
    repo.update(UID, SID)
    assert pool.log == []
    repo.update(UID, SID, score_breakdown={"eligibility_score": 5}, score_after=80)
    sql, params = pool.log[0]
    assert sql.startswith("update public.cv_sessions set ")
    assert params["score_breakdown"].obj == {"eligibility_score": 5}
    assert params["score_after"] == 80


def test_get_maps_a_row():
    now = datetime.now(UTC)
    row = {
        "id": SID,
        "user_id": UID,
        "status": "succeeded",
        "awaiting_kind": None,
        "jd_text": "jd",
        "jd_domain": "tech",
        "template_id": "classic",
        "options": None,
        "source_cv": None,
        "score_before": None,
        "score_after": 80,
        "score_breakdown": {"eligibility_score": 70},
        "tailored_cv": None,
        "cover_letter_text": None,
        "current_render_id": None,
        "pipeline_summary": None,
        "created_at": now,
        "pdf_path": f"{UID}/{SID}/cv.pdf",
        "cover_letter_pdf_path": None,
    }
    got = PgSessionRepo(RecordingPool(rows=[row])).get(UID, SID)
    assert got is not None
    assert (got.id, got.score_after, got.options, got.created_at) == (SID, 80, {}, now)
    assert got.pdf_path == f"{UID}/{SID}/cv.pdf"


def test_list_is_newest_first_and_light():
    pool = RecordingPool()
    PgSessionRepo(pool).list_for_user(UID, limit=10)
    sql, params = pool.log[0]
    assert "order by s.created_at desc" in sql
    assert "s.tailored_cv" not in sql and "s.source_cv" not in sql
    assert params["limit"] == 10


def test_render_add_reuses_the_same_users_row_on_hash_conflict():
    pool = RecordingPool(rows=[{"id": "existing"}])
    rid = PgRenderRepo(pool).add(UID, SID, pdf_path="p", content_hash="h", template_id="classic")
    assert rid == "existing"
    sql = pool.log[0][0]
    assert "on conflict (content_hash) do nothing" in sql
    assert (
        "content_hash = %(content_hash)s and user_id = %(user_id)s "
        "and session_id = %(session_id)s" in sql
    )


def test_render_add_retries_once_after_a_concurrent_insert_race():
    class _Race(RecordingPool):
        def __init__(self):
            super().__init__()
            self.results = [[], [{"id": "winner"}]]

        def connection(self, timeout=None):
            self.rows = self.results.pop(0)
            return super().connection(timeout)

    pool = _Race()
    assert PgRenderRepo(pool).add(UID, SID, pdf_path="p", content_hash="h", template_id="c") == (
        "winner"
    )
    assert len(pool.log) == 2
    retry_sql, params = pool.log[1]
    assert retry_sql.startswith("select") and "session_id = %(session_id)s" in retry_sql
    assert params["user_id"] == UID


def test_render_add_hash_owned_by_someone_else_is_a_conflict():
    with pytest.raises(DbConflict):
        PgRenderRepo(RecordingPool()).add(
            UID, SID, pdf_path="p", content_hash="h", template_id="classic"
        )


def test_credit_balance_defaults_and_maps():
    assert PgCreditRepo(RecordingPool()).balance(UID) == (0, 0)
    assert PgCreditRepo(RecordingPool(rows=[{"balance": 9, "held": 2}])).balance(UID) == (9, 2)


def test_credit_ledger_is_newest_first_with_limit():
    pool = RecordingPool(rows=[{"id": 1, "kind": "signup_bonus"}])
    assert PgCreditRepo(pool).ledger(UID, limit=5) == [{"id": 1, "kind": "signup_bonus"}]
    sql, params = pool.log[0]
    assert "order by created_at desc, id desc" in sql
    assert params["limit"] == 5


def test_credit_grant_calls_the_sql_function():
    pool = RecordingPool(rows=[{"balance": 100}])
    assert PgCreditRepo(pool).grant(UID, 100, "signup_bonus", f"signup_bonus:{UID}") == 100
    sql, params = pool.log[0]
    assert "public.credits_grant(%(user_id)s, %(amount)s, %(kind)s, %(idem)s)" in sql
    assert params == {
        "user_id": UID,
        "amount": 100,
        "kind": "signup_bonus",
        "idem": f"signup_bonus:{UID}",
    }


def test_credit_grant_function_rejection_is_a_value_error():
    class _Raising(RecordingPool):
        def connection(self, timeout=None):
            raise psycopg.errors.RaiseException("IDEMPOTENCY_MISMATCH secret")

    with pytest.raises(ValueError) as ei:
        PgCreditRepo(_Raising()).grant(UID, 1, "purchase", "k")
    assert "secret" not in str(ei.value)


def test_session_repo_accepts_uuid7_ids():
    pool = RecordingPool()
    PgSessionRepo(pool).get(UID, uuid7())
    assert len(pool.log) == 1


def test_session_ids_scoped_by_user_and_returns_ids():
    pool = RecordingPool(rows=[{"id": SID}])
    assert PgSessionRepo(pool).session_ids(UID) == [SID]
    ((sql, params),) = pool.log
    assert_user_scoped(sql)
    assert params == {"user_id": UID}
    assert "limit" not in sql.lower()
