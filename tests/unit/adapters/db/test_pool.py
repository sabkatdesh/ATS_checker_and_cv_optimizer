from pydantic import SecretStr

from app.adapters.db.pool import db_health, make_pool
from app.config.db_settings import DbSettings
from tests.fakes.recording_pool import RecordingPool


def test_make_pool_is_lazy_and_configured():
    s = DbSettings(dsn=SecretStr("postgresql://u:pw@localhost:1/db"), pool_max=3)
    pool = make_pool(s)
    try:
        assert pool.closed  # open=False: no connection attempted
        assert pool.max_size == 3
        assert pool.kwargs["application_name"] == "cv-api"
        assert "pw" not in repr(pool.name)
    finally:
        pool.close()


def test_db_health_true_and_never_raises():
    pool = RecordingPool()
    assert db_health(pool) is True  # type: ignore[arg-type]
    pool.raise_on_connect = RuntimeError("boom password=x")
    assert db_health(pool) is False  # type: ignore[arg-type]
