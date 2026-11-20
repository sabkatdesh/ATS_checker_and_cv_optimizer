"""renders rows (render cache). content_hash is globally unique; reuse is per user only."""

from typing import Any

from app.adapters.db.errors import DbConflict, map_db_errors

# The second select sees the statement's starting snapshot, so it only finds an older row.
_ADD = (
    "with ins as ("
    "insert into public.renders (session_id, user_id, pdf_path, content_hash, template_id) "
    "values (%(session_id)s, %(user_id)s, %(pdf_path)s, %(content_hash)s, %(template_id)s) "
    "on conflict (content_hash) do nothing returning id) "
    "select id::text as id from ins "
    "union all "
    "select id::text as id from public.renders "
    "where content_hash = %(content_hash)s and user_id = %(user_id)s "
    "limit 1"
)


class PgRenderRepo:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def add(
        self, user_id: str, session_id: str, *, pdf_path: str, content_hash: str, template_id: str
    ) -> str:
        params = {
            "user_id": user_id,
            "session_id": session_id,
            "pdf_path": pdf_path,
            "content_hash": content_hash,
            "template_id": template_id,
        }
        with map_db_errors(), self._pool.connection() as conn:
            row = conn.execute(_ADD, params).fetchone()
        if not row:
            raise DbConflict  # the hash belongs to another user's render
        return str(row["id"])
