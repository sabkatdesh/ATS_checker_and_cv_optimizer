"""Map psycopg failures to constant-message domain errors (no DSN, password or SQL text)."""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
import psycopg_pool


class DbUnavailable(Exception):
    def __init__(self) -> None:
        super().__init__("Database unavailable")


class DbConflict(Exception):
    def __init__(self) -> None:
        super().__init__("Database conflict")


_CONFLICTS = (
    psycopg.errors.UniqueViolation,
    psycopg.errors.ForeignKeyViolation,
    psycopg.errors.SerializationFailure,
    psycopg.errors.DeadlockDetected,
)


@contextmanager
def map_db_errors() -> Iterator[None]:
    try:
        yield
    except (DbUnavailable, DbConflict):
        raise
    except _CONFLICTS:
        raise DbConflict from None
    except (psycopg.Error, psycopg_pool.PoolTimeout, psycopg_pool.PoolClosed):
        raise DbUnavailable from None
