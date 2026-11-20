"""Pick the checkpointer for the configured environment (ADR-007)."""

from collections.abc import Callable

from psycopg_pool import ConnectionPool

from app.adapters.db.checkpointer_pg import PostgresCheckpointerFactory
from app.config.settings import AppSettings, ConfigError
from app.pipeline.checkpointer import CheckpointerFactory, MemoryCheckpointerFactory


def select_checkpointer(
    settings: AppSettings, pool: Callable[[], ConnectionPool]
) -> CheckpointerFactory:
    """Postgres when a DSN is configured; in-memory only in dev/test (lost on restart)."""
    db = settings.db
    if db.dsn is not None:
        return PostgresCheckpointerFactory(
            db.dsn,
            pool(),
            connect_timeout_s=db.connect_timeout_s,
            statement_timeout_ms=db.statement_timeout_ms,
        )
    if settings.env in ("dev", "test"):
        return MemoryCheckpointerFactory()
    raise ConfigError(f"Pipeline checkpoints need DB__DSN when env={settings.env}")
