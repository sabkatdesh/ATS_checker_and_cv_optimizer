"""Sync psycopg pool for the app_backend role. Opened lazily; never logs the DSN."""

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config.db_settings import DbSettings

APPLICATION_NAME = "cv-api"
HEALTH_TIMEOUT_S = 3.0


def make_pool(s: DbSettings) -> ConnectionPool:
    if s.dsn is None:
        raise ValueError("DbSettings.dsn is required")
    statement_timeout_ms = int(s.statement_timeout_ms)

    def configure(conn: psycopg.Connection) -> None:
        conn.execute(
            "select set_config('statement_timeout', %s, false)", (str(statement_timeout_ms),)
        )
        conn.commit()

    return ConnectionPool(
        conninfo=s.dsn.get_secret_value(),
        min_size=1,
        max_size=s.pool_max,
        timeout=s.connect_timeout_s,
        open=False,
        configure=configure,
        name=APPLICATION_NAME,
        kwargs={
            "row_factory": dict_row,
            "application_name": APPLICATION_NAME,
            "connect_timeout": max(1, int(s.connect_timeout_s)),
        },
    )


def db_health(pool: ConnectionPool) -> bool:
    try:
        with pool.connection(timeout=HEALTH_TIMEOUT_S) as conn:
            conn.execute("select 1")
        return True
    except Exception:
        return False
