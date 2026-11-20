"""cv_sessions access for app_backend. Every query is scoped by user_id; ids are UUIDv7 text.

PDF paths come from renders: the CV via current_render_id, the cover letter via its renders
row marked template_id = 'cover_letter'. Both joins also require the same user_id.
"""

from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from app.adapters.db.errors import map_db_errors
from app.ports.repositories import (
    SESSION_JSON_COLUMNS,
    SESSION_UPDATABLE,
    JsonDict,
    SessionRow,
    is_uuid,
)

_LIGHT = (
    "s.id::text as id, s.user_id::text as user_id, s.status, s.awaiting_kind, s.jd_text, "
    "s.jd_domain, s.template_id, s.options, s.score_before, s.score_after, s.score_breakdown, "
    "s.cover_letter_text, s.current_render_id::text as current_render_id, s.created_at, "
    "r.pdf_path as pdf_path, "
    "(select c.pdf_path from public.renders c where c.session_id = s.id "
    "and c.user_id = s.user_id and c.template_id = 'cover_letter' "
    "order by c.created_at desc limit 1) as cover_letter_pdf_path"
)
_HEAVY = _LIGHT + ", s.source_cv, s.tailored_cv, s.pipeline_summary"
_FROM = (
    "from public.cv_sessions s left join public.renders r "
    "on r.id = s.current_render_id and r.user_id = s.user_id"
)
_GET = f"select {_HEAVY} {_FROM} where s.user_id = %(user_id)s and s.id = %(session_id)s"
_LIST = (
    f"select {_LIGHT} {_FROM} where s.user_id = %(user_id)s "
    "order by s.created_at desc limit %(limit)s"
)
_CREATE = (
    "insert into public.cv_sessions "
    "(id, user_id, status, jd_text, source_cv, options, template_id) "
    "values (%(session_id)s, %(user_id)s, 'running', %(jd_text)s, %(source_cv)s, "
    "%(options)s, %(template_id)s)"
)


def _row(r: JsonDict) -> SessionRow:
    created = r.get("created_at")
    return SessionRow(
        id=r["id"],
        user_id=r["user_id"],
        status=r["status"],
        awaiting_kind=r.get("awaiting_kind"),
        jd_text=r.get("jd_text"),
        jd_domain=r.get("jd_domain"),
        template_id=r.get("template_id"),
        options=dict(r.get("options") or {}),
        source_cv=r.get("source_cv"),
        score_before=r.get("score_before"),
        score_after=r.get("score_after"),
        score_breakdown=r.get("score_breakdown"),
        tailored_cv=r.get("tailored_cv"),
        cover_letter_text=r.get("cover_letter_text"),
        current_render_id=r.get("current_render_id"),
        pipeline_summary=r.get("pipeline_summary"),
        created_at=created if isinstance(created, datetime) else None,
        pdf_path=r.get("pdf_path"),
        cover_letter_pdf_path=r.get("cover_letter_pdf_path"),
    )


def check_update_columns(fields: JsonDict) -> None:
    unknown = sorted(set(fields) - SESSION_UPDATABLE)
    if unknown:
        raise ValueError(f"cv_sessions columns not updatable: {', '.join(unknown)}")


class PgSessionRepo:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def create(
        self,
        user_id: str,
        session_id: str,
        *,
        jd_text: str,
        source_cv: JsonDict,
        options: JsonDict,
        template_id: str,
    ) -> None:
        if not is_uuid(session_id):
            raise ValueError("session_id must be a canonical UUID")
        params = {
            "user_id": user_id,
            "session_id": session_id,
            "jd_text": jd_text,
            "source_cv": Jsonb(source_cv),
            "options": Jsonb(options),
            "template_id": template_id,
        }
        with map_db_errors(), self._pool.connection() as conn:
            conn.execute(_CREATE, params)

    def get(self, user_id: str, session_id: str) -> SessionRow | None:
        if not is_uuid(session_id):
            return None
        with map_db_errors(), self._pool.connection() as conn:
            r = conn.execute(_GET, {"user_id": user_id, "session_id": session_id}).fetchone()
        return _row(r) if r else None

    def list_for_user(self, user_id: str, limit: int = 50) -> list[SessionRow]:
        with map_db_errors(), self._pool.connection() as conn:
            rows = conn.execute(_LIST, {"user_id": user_id, "limit": limit}).fetchall()
        return [_row(r) for r in rows]

    def update(self, user_id: str, session_id: str, **fields: Any) -> None:
        check_update_columns(fields)
        if not fields or not is_uuid(session_id):
            return
        # Column names come only from the allow-list above, never from input.
        assignments = ", ".join(f"{col} = %({col})s" for col in fields)
        sql = (
            f"update public.cv_sessions set {assignments} "  # noqa: S608
            "where user_id = %(user_id)s and id = %(session_id)s"
        )
        params: JsonDict = {
            col: Jsonb(v) if col in SESSION_JSON_COLUMNS and v is not None else v
            for col, v in fields.items()
        }
        params.update(user_id=user_id, session_id=session_id)
        with map_db_errors(), self._pool.connection() as conn:
            conn.execute(sql, params)
