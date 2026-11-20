"""Signup-guard counters. Bumps go through guard_bump() (definer), reads hit the table."""

from datetime import date
from typing import Any

from app.adapters.db.errors import map_db_errors

_COUNTS = (
    "select bucket, count from public.signup_guards "
    "where bucket = any(%(buckets)s) and day = %(day)s"
)
_BUMP = "select public.guard_bump(%(buckets)s, %(day)s)"


class PgGuardRepo:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def counts(self, ip_bucket: str, device_bucket: str | None, day: date) -> tuple[int, int]:
        buckets = [ip_bucket] + ([device_bucket] if device_bucket else [])
        with map_db_errors(), self._pool.connection() as conn:
            rows = conn.execute(_COUNTS, {"buckets": buckets, "day": day}).fetchall()
        by_bucket = {r["bucket"]: int(r["count"]) for r in rows}
        return by_bucket.get(ip_bucket, 0), by_bucket.get(device_bucket or "", 0)

    def bump(self, buckets: list[str], day: date) -> None:
        if not buckets:
            return
        with map_db_errors(), self._pool.connection() as conn:
            conn.execute(_BUMP, {"buckets": buckets, "day": day})
