import psycopg
import pytest

from app.adapters.db.errors import DbConflict, DbUnavailable, map_db_errors
from app.adapters.db.master_profile_repo import PgMasterProfileRepo
from app.adapters.db.profile_repo import PgProfileRepo
from app.adapters.db.template_repo import PgTemplateRepo
from tests.fakes.recording_pool import RecordingPool

UID = "11111111-1111-1111-1111-111111111111"


def _calls(pool: RecordingPool) -> None:
    repo = PgProfileRepo(pool)
    mrepo = PgMasterProfileRepo(pool)
    repo.get_preferences(UID)
    repo.save_preferences(UID, {"accent_color": "#fff"})
    repo.bonus_state(UID)
    repo.mark_bonus(UID, granted=True)
    repo.mark_bonus(UID, granted=False)
    mrepo.get_default(UID)
    mrepo.upsert_default(UID, {"full_name": "A"})


def test_every_repo_query_scopes_by_user():
    pool = RecordingPool()
    _calls(pool)
    assert len(pool.log) == 7
    for sql, params in pool.log:
        assert "%(user_id)s" in sql
        assert params["user_id"] == UID
        if not sql.startswith("insert"):  # inserts bind user_id in VALUES
            assert "user_id = %(user_id)s" in sql


def test_template_query_is_public_and_active_only():
    pool = RecordingPool(rows=[{"id": "classic"}])
    assert PgTemplateRepo(pool).list_active() == [{"id": "classic"}]
    assert "is_active" in pool.log[0][0]


def test_missing_profile_row_gives_empty_prefs_and_default():
    pool = RecordingPool()
    assert PgProfileRepo(pool).get_preferences(UID) == {}
    assert PgMasterProfileRepo(pool).get_default(UID) is None
    state = PgProfileRepo(pool).bonus_state(UID)
    assert (state.verified_at, state.granted_at, state.review_at) == (None, None, None)


def test_master_upsert_uses_partial_unique_index_and_strips_server_fields():
    pool = RecordingPool()
    PgMasterProfileRepo(pool).upsert_default(UID, {"full_name": "A", "user_id": "x"})
    sql, params = pool.log[0]
    assert "on conflict (user_id) where is_default" in sql
    assert params["data"].obj == {"full_name": "A"}


def test_mark_bonus_uses_coalesce():
    pool = RecordingPool()
    repo = PgProfileRepo(pool)
    repo.mark_bonus(UID, granted=True)
    repo.mark_bonus(UID, granted=False)
    assert "coalesce(bonus_granted_at, now())" in pool.log[0][0]
    assert "coalesce(bonus_review_at, now())" in pool.log[1][0]


def test_get_default_adds_user_id():
    pool = RecordingPool(rows=[{"cv_data": {"full_name": "A"}}])
    assert PgMasterProfileRepo(pool).get_default(UID) == {"full_name": "A", "user_id": UID}


def test_db_errors_mapped_to_constant_messages():
    secret = "postgresql://u:hunter2@host/db"
    with pytest.raises(DbUnavailable) as ei, map_db_errors():
        raise psycopg.OperationalError(f"connection failed password=hunter2 {secret}")
    assert "hunter2" not in str(ei.value)
    assert "postgresql" not in str(ei.value)
    assert ei.value.__cause__ is None
    assert ei.value.__suppress_context__


def test_unique_violation_maps_to_conflict():
    with pytest.raises(DbConflict), map_db_errors():
        raise psycopg.errors.UniqueViolation("dup key secret")


def test_repo_maps_pool_failure():
    pool = RecordingPool()
    pool.raise_on_connect = psycopg.OperationalError("password=x")
    with pytest.raises(DbUnavailable):
        PgProfileRepo(pool).get_preferences(UID)
