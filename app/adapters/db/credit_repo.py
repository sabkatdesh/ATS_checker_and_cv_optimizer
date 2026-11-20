"""Credit reads plus credits_grant(). Balances change only through the SQL functions."""

from typing import Any

import psycopg

from app.adapters.db.errors import map_db_errors
from app.ports.repositories import JsonDict

_BALANCE = "select balance, held from public.credit_balances where user_id = %(user_id)s"
_LEDGER = (
    "select id, kind, delta_balance, delta_held, reason, session_id::text as session_id, "
    "created_at from public.credit_ledger where user_id = %(user_id)s "
    "order by created_at desc, id desc limit %(limit)s"
)
_GRANT = "select public.credits_grant(%(user_id)s, %(amount)s, %(kind)s, %(idem)s) as balance"
_GRANT_CODES = (
    "INVALID_IDEMPOTENCY_KEY",
    "INVALID_USER",
    "INVALID_AMOUNT",
    "INVALID_KIND",
    "IDEMPOTENCY_MISMATCH",
)


def _grant_code(exc: Exception) -> str:
    text = str(exc)
    return next((code for code in _GRANT_CODES if code in text), "REJECTED")


class PgCreditRepo:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def balance(self, user_id: str) -> tuple[int, int]:
        with map_db_errors(), self._pool.connection() as conn:
            row = conn.execute(_BALANCE, {"user_id": user_id}).fetchone()
        return (int(row["balance"]), int(row["held"])) if row else (0, 0)

    def ledger(self, user_id: str, limit: int = 50) -> list[JsonDict]:
        with map_db_errors(), self._pool.connection() as conn:
            rows = conn.execute(_LEDGER, {"user_id": user_id, "limit": limit}).fetchall()
        return [dict(r) for r in rows]

    def grant(self, user_id: str, amount: int, kind: str, idem: str) -> int:
        """Function rejections (bad key/kind/amount, key replayed by someone else) -> ValueError."""
        params = {"user_id": user_id, "amount": amount, "kind": kind, "idem": idem}
        try:
            with self._pool.connection() as conn:
                row = conn.execute(_GRANT, params).fetchone()
        except psycopg.errors.RaiseException as exc:
            raise ValueError(f"credits_grant rejected: {_grant_code(exc)}") from None
        except Exception:
            with map_db_errors():
                raise
        return int(row["balance"]) if row else 0
