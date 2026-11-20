"""audit_log inserts (append-only). The actor is nullable: system actions have none."""

from typing import Any

from psycopg.types.json import Jsonb

from app.adapters.db.errors import map_db_errors
from app.ports.repositories import JsonDict

_INSERT = (
    "insert into public.audit_log (actor, action, target, meta) "
    "values (%(actor)s, %(action)s, %(target)s, %(meta)s)"
)


class PgAuditRepo:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def write(self, *, actor: str | None, action: str, target: str | None, meta: JsonDict) -> None:
        params = {"actor": actor, "action": action, "target": target, "meta": Jsonb(meta)}
        with map_db_errors(), self._pool.connection() as conn:
            conn.execute(_INSERT, params)
