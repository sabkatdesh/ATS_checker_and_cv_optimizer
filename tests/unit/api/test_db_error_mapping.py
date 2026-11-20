"""DB failures map by kind: integrity -> 409, bad data -> 422, operational -> 503, else 500."""

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg_pool import PoolTimeout

from app.adapters.db.errors import (
    DbConflict,
    DbFailure,
    DbInvalidData,
    DbUnavailable,
    map_db_errors,
)
from app.api.errors import install_error_handlers

SECRET = "postgresql://u:hunter2pw@db.example.com/postgres"


def _mapped(exc: Exception) -> Exception:
    with pytest.raises(Exception) as info, map_db_errors():
        raise exc
    return info.value


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (psycopg.errors.UniqueViolation(SECRET), DbConflict),
        (psycopg.errors.CheckViolation(SECRET), DbConflict),
        (psycopg.errors.NotNullViolation(SECRET), DbConflict),
        (psycopg.errors.ExclusionViolation(SECRET), DbConflict),
        (psycopg.errors.SerializationFailure(SECRET), DbConflict),
        (psycopg.errors.InvalidTextRepresentation(SECRET), DbInvalidData),
        (psycopg.errors.NumericValueOutOfRange(SECRET), DbInvalidData),
        (psycopg.OperationalError(SECRET), DbUnavailable),
        (psycopg.errors.QueryCanceled(SECRET), DbUnavailable),
        (PoolTimeout(SECRET), DbUnavailable),
        (psycopg.errors.UndefinedColumn(SECRET), DbFailure),
    ],
)
def test_map_db_errors_by_kind(exc, expected):
    got = _mapped(exc)
    assert type(got) is expected
    assert "hunter2pw" not in str(got) and got.__cause__ is None


def _client(exc: Exception) -> TestClient:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/boom")
    def boom():
        raise exc

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (DbInvalidData(), 422, "DB_INVALID_DATA"),
        (psycopg.errors.InvalidTextRepresentation(SECRET), 422, "DB_INVALID_DATA"),
        (psycopg.errors.CheckViolation(SECRET), 409, "DB_CONFLICT"),
        (DbConflict(), 409, "DB_CONFLICT"),
        (DbFailure(), 500, "INTERNAL_ERROR"),
        (DbUnavailable(), 503, "DB_UNAVAILABLE"),
    ],
)
def test_api_problem_json_per_kind(exc, status, code):
    r = _client(exc).get("/boom")
    assert r.status_code == status
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == code
    assert "hunter2pw" not in r.text
