"""master_profiles: the default profile holds the legacy flat /profile dict (ruling E3)."""

from typing import Any

from psycopg.types.json import Jsonb

from app.adapters.db.errors import map_db_errors
from app.ports.repositories import JsonDict

_GET_DEFAULT = (
    "select cv_data from public.master_profiles where user_id = %(user_id)s and is_default"
)
# Top-level merge keeps the legacy semantics: a partial save only replaces the sent fields.
_UPSERT_DEFAULT = (
    "insert into public.master_profiles (user_id, is_default, cv_data) "
    "values (%(user_id)s, true, %(data)s) "
    "on conflict (user_id) where is_default do update "
    "set cv_data = public.master_profiles.cv_data || excluded.cv_data"
)


class PgMasterProfileRepo:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def get_default(self, user_id: str) -> JsonDict | None:
        with map_db_errors(), self._pool.connection() as conn:
            row = conn.execute(_GET_DEFAULT, {"user_id": user_id}).fetchone()
        if not row:
            return None
        return {**(row["cv_data"] or {}), "user_id": user_id}

    def upsert_default(self, user_id: str, data: JsonDict) -> None:
        clean = {k: v for k, v in data.items() if k != "user_id"}
        with map_db_errors(), self._pool.connection() as conn:
            conn.execute(_UPSERT_DEFAULT, {"user_id": user_id, "data": Jsonb(clean)})
