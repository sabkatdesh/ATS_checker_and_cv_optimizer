"""templates: public catalogue (no user scoping)."""

from typing import Any

from app.adapters.db.errors import map_db_errors
from app.ports.repositories import JsonDict

_LIST_ACTIVE = (
    "select id, version, name, description, tier, ats_safe, columns, photo, "
    "recommended_domains, manifest from public.templates where is_active order by id"
)


class PgTemplateRepo:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def list_active(self) -> list[JsonDict]:
        with map_db_errors(), self._pool.connection() as conn:
            return list(conn.execute(_LIST_ACTIVE).fetchall())
