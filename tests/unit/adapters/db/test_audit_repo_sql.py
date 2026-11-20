from app.adapters.db.audit_repo import PgAuditRepo
from tests.fakes.recording_pool import RecordingPool


def test_audit_insert_allows_null_actor():
    pool = RecordingPool()
    PgAuditRepo(pool).write(actor=None, action="account.purged", target="abc", meta={"n": 1})
    ((sql, params),) = pool.log
    assert sql.startswith("insert into public.audit_log")
    assert params["actor"] is None and params["action"] == "account.purged"
    assert params["target"] == "abc"
