import pytest
from pydantic import SecretStr

from app.adapters.db.pool import db_health, make_pool
from app.config.db_settings import DbSettings
from app.config.settings import ConfigError
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


def test_pool_checks_connections_and_disables_prepared_statements():
    from psycopg_pool import ConnectionPool

    pool = make_pool(DbSettings(dsn=SecretStr("postgresql://u:pw@localhost:5432/db")))
    try:
        assert pool._check == ConnectionPool.check_connection  # type: ignore[attr-defined]
        assert pool.kwargs["prepare_threshold"] is None
    finally:
        pool.close()


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://u:hunter2@aws-0-x.pooler.supabase.com:6543/postgres",
        "host=aws-0-x.pooler.supabase.com port=6543 user=u password=hunter2 dbname=postgres",
    ],
)
def test_transaction_pooler_port_is_rejected(dsn):
    with pytest.raises(ConfigError) as exc:
        make_pool(DbSettings(dsn=SecretStr(dsn)))
    assert "session pooler" in str(exc.value)
    assert "hunter2" not in str(exc.value) and "supabase.com" not in str(exc.value)


def test_unparsable_dsn_is_a_constant_config_error():
    with pytest.raises(ConfigError) as exc:
        make_pool(DbSettings(dsn=SecretStr("host=a password='hunter2")))
    assert "hunter2" not in str(exc.value)
