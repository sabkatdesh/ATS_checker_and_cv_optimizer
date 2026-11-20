"""In-memory cv_sessions and renders mirroring the Pg adapters (user scoping, allow-list)."""

from dataclasses import fields as dc_fields
from datetime import UTC, datetime, timedelta
from typing import Any

from app.adapters.db.errors import DbConflict
from app.adapters.db.session_repo import check_update_columns
from app.domain.common import uuid7
from app.ports.repositories import COVER_LETTER_RENDER, JsonDict, SessionRow, is_uuid

_ROW_FIELDS = {f.name for f in dc_fields(SessionRow)} - {"pdf_path", "cover_letter_pdf_path"}


class MemoryRenderRepo:
    def __init__(self) -> None:
        self.rows: dict[str, JsonDict] = {}

    def add(
        self, user_id: str, session_id: str, *, pdf_path: str, content_hash: str, template_id: str
    ) -> str:
        for rid, row in self.rows.items():
            if row["content_hash"] == content_hash:
                if (row["user_id"], row["session_id"]) != (user_id, session_id):
                    raise DbConflict
                return rid
        rid = uuid7()
        self.rows[rid] = {
            "id": rid,
            "session_id": session_id,
            "user_id": user_id,
            "pdf_path": pdf_path,
            "content_hash": content_hash,
            "template_id": template_id,
            "created_at": datetime.now(UTC),
        }
        return rid

    def cv_path_for(self, user_id: str, session_id: str, render_id: str | None) -> str | None:
        row = self.rows.get(render_id or "")
        owned = row and (row["user_id"], row["session_id"]) == (user_id, session_id)
        return row["pdf_path"] if owned and row else None

    def cover_letter_path(self, user_id: str, session_id: str) -> str | None:
        rows = [
            r
            for r in self.rows.values()
            if r["session_id"] == session_id
            and r["user_id"] == user_id
            and r["template_id"] == COVER_LETTER_RENDER
        ]
        return max(rows, key=lambda r: r["created_at"])["pdf_path"] if rows else None


class MemorySessionRepo:
    def __init__(self, renders: MemoryRenderRepo | None = None) -> None:
        self.rows: dict[str, JsonDict] = {}
        self.renders = renders if renders is not None else MemoryRenderRepo()
        self.calls: list[tuple[str, tuple[Any, ...], JsonDict]] = []
        self.raise_on: dict[str, Exception] = {}

    def _enter(self, name: str, args: tuple[Any, ...], kwargs: JsonDict) -> None:
        self.calls.append((name, args, kwargs))
        if name in self.raise_on:
            raise self.raise_on[name]

    def seed(self, user_id: str, session_id: str | None = None, **cols: Any) -> str:
        """Test helper: insert a row directly (status defaults to running)."""
        sid = session_id or uuid7()
        unknown = set(cols) - _ROW_FIELDS
        if unknown:
            raise ValueError(f"unknown cv_sessions column(s): {sorted(unknown)}")
        # Seeded rows get strictly increasing created_at so ordering is deterministic.
        created = datetime.now(UTC) + timedelta(microseconds=len(self.rows))
        self.rows[sid] = {
            "status": "running",
            "options": {},
            "created_at": created,
            **cols,
            "id": sid,
            "user_id": user_id,
        }
        return sid

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
        kwargs = {
            "jd_text": jd_text,
            "source_cv": source_cv,
            "options": options,
            "template_id": template_id,
        }
        self._enter("create", (user_id, session_id), kwargs)
        if not is_uuid(session_id):
            raise ValueError("session_id must be a canonical UUID")
        if session_id in self.rows:
            raise DbConflict
        self.seed(user_id, session_id, **{**kwargs, "options": dict(options)})

    def _owned(self, user_id: str, session_id: str) -> JsonDict | None:
        if not is_uuid(session_id):
            return None
        row = self.rows.get(session_id)
        return row if row and row["user_id"] == user_id else None

    def _to_row(self, row: JsonDict) -> SessionRow:
        user_id, sid = row["user_id"], row["id"]
        return SessionRow(
            **{k: v for k, v in row.items() if k in _ROW_FIELDS},
            pdf_path=self.renders.cv_path_for(user_id, sid, row.get("current_render_id")),
            cover_letter_pdf_path=self.renders.cover_letter_path(user_id, sid),
        )

    def get(self, user_id: str, session_id: str) -> SessionRow | None:
        self._enter("get", (user_id, session_id), {})
        row = self._owned(user_id, session_id)
        return self._to_row(row) if row else None

    def list_for_user(self, user_id: str, limit: int = 50) -> list[SessionRow]:
        self._enter("list_for_user", (user_id,), {"limit": limit})
        mine = [r for r in self.rows.values() if r["user_id"] == user_id]
        mine.sort(key=lambda r: (r["created_at"], r["id"]), reverse=True)
        return [self._to_row(r) for r in mine[:limit]]

    def update(self, user_id: str, session_id: str, **fields: Any) -> None:
        self._enter("update", (user_id, session_id), fields)
        check_update_columns(fields)
        row = self._owned(user_id, session_id)
        if row is not None:
            row.update(fields)

    def raw(self, session_id: str) -> JsonDict:
        """Test helper: the stored columns of one row, regardless of owner."""
        return self.rows[session_id]
