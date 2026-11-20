import psycopg
import pytest

from app.adapters.db.guard_repo import PgGuardRepo
from tests.fakes.recording_pool import RecordingPool

UID = "11111111-1111-4111-8111-111111111111"


def test_claim_calls_the_single_atomic_function():
    pool = RecordingPool(rows=[{"outcome": "granted"}])
    out = PgGuardRepo(pool).claim(UID, "ip:a", "device:b", ip_max=3, device_max=1, amount=100)
    assert out == "granted"
    sql, params = pool.log[0]
    assert "public.claim_signup_bonus(" in sql
    assert params == {
        "user_id": UID,
        "ip": "ip:a",
        "dev": "device:b",
        "ip_max": 3,
        "dev_max": 1,
        "amount": 100,
    }


def test_claim_without_device_passes_null():
    pool = RecordingPool(rows=[{"outcome": "pending_review"}])
    PgGuardRepo(pool).claim(UID, "ip:a", None, ip_max=3, device_max=1, amount=100)
    assert pool.log[0][1]["dev"] is None


def test_claim_rejection_is_value_error_without_details():
    pool = RecordingPool()
    pool.raise_on_connect = psycopg.errors.RaiseException("INVALID_USER secret")
    with pytest.raises(ValueError) as exc:
        PgGuardRepo(pool).claim(UID, "ip:a", None, ip_max=3, device_max=1, amount=100)
    assert "secret" not in str(exc.value)
