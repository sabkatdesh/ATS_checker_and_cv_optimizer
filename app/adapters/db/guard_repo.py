"""Signup bonus claim: guards and grant in one SQL function (one transaction)."""

from typing import Any

import psycopg

from app.adapters.db.errors import map_db_errors

_CLAIM = (
    "select public.claim_signup_bonus(%(user_id)s, %(ip)s, %(dev)s, "
    "%(ip_max)s, %(dev_max)s, %(amount)s) as outcome"
)


class PgGuardRepo:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def claim(
        self,
        user_id: str,
        ip_bucket: str,
        device_bucket: str | None,
        *,
        ip_max: int,
        device_max: int,
        amount: int,
    ) -> str:
        """Outcome string. Function rejections (bad user/bucket) -> ValueError, no details."""
        params = {
            "user_id": user_id,
            "ip": ip_bucket,
            "dev": device_bucket,
            "ip_max": ip_max,
            "dev_max": device_max,
            "amount": amount,
        }
        try:
            with self._pool.connection() as conn:
                row = conn.execute(_CLAIM, params).fetchone()
        except psycopg.errors.RaiseException:
            raise ValueError("claim_signup_bonus rejected") from None
        except Exception:
            with map_db_errors():
                raise
        return str(row["outcome"]) if row else "pending_review"
