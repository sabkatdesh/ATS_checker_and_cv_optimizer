"""Sync psycopg pool for the app_backend role. Opened lazily; never logs the DSN."""

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config.db_settings import DbSettings
from app.config.settings import ConfigError

APPLICATION_NAME = "cv-api"
HEALTH_TIMEOUT_S = 3.0
TRANSACTION_POOLER_PORT = "6543"
_TRANSACTION_POOLER = (
    "DB__DSN must use the Supabase session pooler (port 5432); "
    "the transaction pooler (port 6543) is not supported"
)


def _reject_transaction_pooler(dsn: str) -> None:
    """Transaction mode drops per-connection settings and breaks prepared statements."""
    try:
        port = str(conninfo_to_dict(dsn).get("port") or "")
    except psycopg.ProgrammingError:
        raise ConfigError("DB__DSN is not a valid connection string") from None
    if TRANSACTION_POOLER_PORT in port.split(","):
        raise ConfigError(_TRANSACTION_POOLER)


def make_pool(s: DbSettings) -> ConnectionPool:
    if s.dsn is None:
        raise ValueError("DbSettings.dsn is required")
    _reject_transaction_pooler(s.dsn.get_secret_value())
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
        check=ConnectionPool.check_connection,
        name=APPLICATION_NAME,
        kwargs={
            "row_factory": dict_row,
            # Safe behind any pooler; also avoids stale server-side statements on reconnect.
            "prepare_threshold": None,
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
