"""PgSessionRepo.transition(): a compare-and-set on status (and awaiting_kind)."""

from app.adapters.db.session_repo import PgSessionRepo
from tests.fakes.memory_session_repos import MemorySessionRepo
from tests.fakes.recording_pool import RecordingPool, assert_user_scoped

UID = "11111111-1111-1111-1111-111111111111"
SID = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b"


def test_transition_is_a_guarded_update_returning_the_winner():
    pool = RecordingPool(rowcount=1)
    won = PgSessionRepo(pool).transition(UID, SID, "awaiting_input", "questions", "running")
    assert won is True
    sql, params = pool.log[0]
    assert_user_scoped(sql)
    assert "and id = %(session_id)s" in sql
    assert "and status = %(from_status)s" in sql
    assert "and awaiting_kind = %(from_kind)s" in sql
    assert "awaiting_kind = null" in sql
    assert params == {
        "user_id": UID,
        "session_id": SID,
        "from_status": "awaiting_input",
        "from_kind": "questions",
        "to_status": "running",
    }


def test_transition_loser_gets_false():
    pool = RecordingPool(rowcount=0)
    assert not PgSessionRepo(pool).transition(UID, SID, "awaiting_input", "questions", "running")


def test_transition_without_kind_does_not_filter_on_it():
    pool = RecordingPool()
    PgSessionRepo(pool).transition(UID, SID, "running", None, "failed")
    assert "from_kind" not in pool.log[0][0]


def test_transition_malformed_id_is_false_without_a_query():
    pool = RecordingPool()
    assert not PgSessionRepo(pool).transition(UID, "nope", "running", None, "failed")
    assert pool.log == []


def test_memory_transition_matches_once_and_accepts_upper_case_ids():
    repo = MemorySessionRepo()
    repo.seed(UID, SID, status="awaiting_input", awaiting_kind="questions")
    args = ("awaiting_input", "questions", "running")
    assert repo.transition(UID, SID.upper(), *args) is True
    assert repo.transition(UID, SID, *args) is False
    assert (repo.raw(SID)["status"], repo.raw(SID)["awaiting_kind"]) == ("running", None)
    assert repo.get(UID, SID.upper()) is not None
    assert repo.transition("someone-else", SID, "running", None, "failed") is False
