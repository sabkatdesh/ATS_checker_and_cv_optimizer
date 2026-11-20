"""The app's Pg repositories scope every query by user_id, on the real SQL.

app_backend has BYPASSRLS, so user scoping here rests on the repositories' WHERE clauses alone;
these tests are what proves them against the live schema.
"""

from app.adapters.db.credit_repo import PgCreditRepo
from app.adapters.db.master_profile_repo import PgMasterProfileRepo
from app.adapters.db.session_repo import PgSessionRepo
from app.domain.common import uuid7
from tests.remote._helpers import Conn, grant, new_key, scalar


def test_repo_cannot_read_other_user_session(user_a, user_b, backend_pool, backend_conn: Conn):
    repo = PgSessionRepo(backend_pool)
    sid = uuid7()
    repo.create(
        user_a.id, sid, jd_text="m4test jd", source_cv={"k": 1}, options={}, template_id="classic"
    )
    mine = repo.get(user_a.id, sid)
    assert mine is not None and mine.user_id == user_a.id and mine.status == "running"
    assert repo.get(user_b.id, sid) is None
    assert sid not in {s.id for s in repo.list_for_user(user_b.id)}
    assert sid not in repo.session_ids(user_b.id)
    assert sid in repo.session_ids(user_a.id)

    repo.update(user_b.id, sid, status="failed")  # B's update matches nothing
    assert scalar(backend_conn, "select status from public.cv_sessions where id = %s", (sid,)) == (
        "running"
    )
    repo.update(user_a.id, sid, status="awaiting_input")
    got = repo.get(user_a.id, sid)
    assert got is not None and got.status == "awaiting_input"


def test_master_profile_repo_is_user_scoped(user_a, user_b, backend_pool) -> None:
    repo = PgMasterProfileRepo(backend_pool)
    repo.upsert_default(user_a.id, {"meta": {"full_name": "M4 Test"}})
    repo.upsert_default(user_a.id, {"skills": ["sql"]})  # top-level merge
    got = repo.get_default(user_a.id)
    assert got == {"meta": {"full_name": "M4 Test"}, "skills": ["sql"], "user_id": user_a.id}
    assert repo.get_default(user_b.id) is None


def test_credit_repo_reads_only_own_rows(user_a, user_b, backend_pool, backend_conn) -> None:
    grant(backend_conn, user_a.id, 25, new_key("repo"))
    repo = PgCreditRepo(backend_pool)
    assert repo.balance(user_a.id) == (25, 0)
    assert repo.balance(user_b.id) == (0, 0)
    assert len(repo.ledger(user_a.id)) == 1
    assert repo.ledger(user_b.id) == []
