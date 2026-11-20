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


class DbInvalidData(Exception):
    """A value the database cannot store (bad text representation, out of range, ...)."""

    def __init__(self) -> None:
        super().__init__("Invalid data")


class DbFailure(Exception):
    """Any other database error (a bug, not an outage): retrying will not help."""

    def __init__(self) -> None:
        super().__init__("Database error")


DB_ERRORS = (DbUnavailable, DbConflict, DbInvalidData, DbFailure)

# Every integrity violation (unique, FK, check, not-null, exclusion) plus the
# retryable concurrency failures.
_CONFLICTS = (
    psycopg.IntegrityError,
    psycopg.errors.SerializationFailure,
    psycopg.errors.DeadlockDetected,
)
_UNAVAILABLE = (
    psycopg.OperationalError,
    psycopg.InterfaceError,
    psycopg_pool.PoolTimeout,
    psycopg_pool.PoolClosed,
)


@contextmanager
def map_db_errors() -> Iterator[None]:
    try:
        yield
    except DB_ERRORS:
        raise
    except _CONFLICTS:
        raise DbConflict from None
    except psycopg.DataError:
        raise DbInvalidData from None
    except _UNAVAILABLE:
        raise DbUnavailable from None
    except psycopg.Error:
        raise DbFailure from None
