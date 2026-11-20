"""profiles-scoped access: preferences (settings) and signup-bonus state."""

from typing import Any

from psycopg.types.json import Jsonb

from app.adapters.db.errors import DbConflict, map_db_errors
from app.ports.repositories import BonusState, JsonDict

_GET_PREFS = "select preferences from public.profiles where user_id = %(user_id)s"
# Update only: the signup trigger and the 0800 backfill create every profiles row with its
# email_verified_at. Inserting here could create a row that never learns the user is verified.
_SAVE_PREFS = (
    "update public.profiles set preferences = preferences || %(prefs)s where user_id = %(user_id)s"
)
_BONUS_STATE = (
    "select email_verified_at, bonus_granted_at, bonus_review_at "
    "from public.profiles where user_id = %(user_id)s"
)
_MARK_GRANTED = (
    "update public.profiles set bonus_granted_at = coalesce(bonus_granted_at, now()) "
    "where user_id = %(user_id)s"
)
_MARK_REVIEW = (
    "update public.profiles set bonus_review_at = coalesce(bonus_review_at, now()) "
    "where user_id = %(user_id)s"
)


class PgProfileRepo:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def get_preferences(self, user_id: str) -> JsonDict:
        with map_db_errors(), self._pool.connection() as conn:
            row = conn.execute(_GET_PREFS, {"user_id": user_id}).fetchone()
        return dict(row["preferences"] or {}) if row else {}

    def save_preferences(self, user_id: str, prefs: JsonDict) -> None:
        with map_db_errors(), self._pool.connection() as conn:
            cur = conn.execute(_SAVE_PREFS, {"user_id": user_id, "prefs": Jsonb(prefs)})
            if cur.rowcount != 1:
                raise DbConflict

    def bonus_state(self, user_id: str) -> BonusState:
        with map_db_errors(), self._pool.connection() as conn:
            row = conn.execute(_BONUS_STATE, {"user_id": user_id}).fetchone()
        if not row:
            return BonusState(None, None, None)
        return BonusState(row["email_verified_at"], row["bonus_granted_at"], row["bonus_review_at"])

    def mark_bonus(self, user_id: str, *, granted: bool) -> None:
        sql = _MARK_GRANTED if granted else _MARK_REVIEW
        with map_db_errors(), self._pool.connection() as conn:
            conn.execute(sql, {"user_id": user_id})
