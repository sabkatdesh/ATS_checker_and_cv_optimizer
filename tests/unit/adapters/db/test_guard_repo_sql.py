from datetime import date

from app.adapters.db.guard_repo import PgGuardRepo
from tests.fakes.recording_pool import RecordingPool

DAY = date(2026, 11, 20)


def test_counts_reads_both_buckets_for_the_day():
    pool = RecordingPool(rows=[{"bucket": "ip:a", "count": 2}, {"bucket": "device:b", "count": 1}])
    assert PgGuardRepo(pool).counts("ip:a", "device:b", DAY) == (2, 1)
    sql, params = pool.log[0]
    assert "public.signup_guards" in sql and "day = %(day)s" in sql
    assert params == {"buckets": ["ip:a", "device:b"], "day": DAY}


def test_counts_missing_rows_are_zero_and_device_optional():
    pool = RecordingPool(rows=[])
    assert PgGuardRepo(pool).counts("ip:a", None, DAY) == (0, 0)
    assert pool.log[0][1]["buckets"] == ["ip:a"]


def test_bump_calls_the_definer_function():
    pool = RecordingPool()
    PgGuardRepo(pool).bump(["ip:a", "device:b"], DAY)
    sql, params = pool.log[0]
    assert "public.guard_bump(%(buckets)s, %(day)s)" in sql
    assert params == {"buckets": ["ip:a", "device:b"], "day": DAY}


def test_bump_with_no_buckets_does_nothing():
    pool = RecordingPool()
    PgGuardRepo(pool).bump([], DAY)
    assert pool.log == []
