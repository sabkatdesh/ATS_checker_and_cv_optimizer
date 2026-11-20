"""One row per MATRIX table for a user, written as app_backend, plus explicit cleanup.

Deleting the Auth user cascades through profiles to every user-owned row. The rest needs an
explicit delete: rows with no user link (templates, signup_guards, payment_events,
feature_flags) and rows whose user link is SET NULL on delete (llm_calls, payment_intents,
audit_log). credit_ledger rows can never be deleted (append-only); they stay anonymised.
"""

from dataclasses import dataclass, field

from app.domain.common import uuid7
from tests.remote._helpers import Conn, grant, insert_session, new_key, reserve, scalar

# A small valid object per bucket (each bucket restricts MIME types).
BUCKET_TYPES: dict[str, tuple[str, bytes]] = {
    "photos": ("image/png", b"\x89PNG\r\n\x1a\nm4test"),
    "renders": ("application/pdf", b"%PDF-1.4 m4test"),
    "imports": ("application/pdf", b"%PDF-1.4 m4test"),
    "exports": ("application/zip", b"PK\x03\x04m4test"),
}

# Tables the purge must leave empty for the user, with how a row is tied to the user.
USER_LINK: dict[str, str] = {
    "profiles": "user_id = %(uid)s",
    "master_profiles": "user_id = %(uid)s",
    "photos": "user_id = %(uid)s",
    "cv_sessions": "user_id = %(uid)s",
    "jobs": "user_id = %(uid)s",
    "job_events": "job_id = any(%(jobs)s::uuid[])",
    "renders": "user_id = %(uid)s",
    "credit_balances": "user_id = %(uid)s",
    "credit_ledger": "user_id = %(uid)s",
    "credit_reservations": "user_id = %(uid)s",
    "llm_calls": "user_id = %(uid)s",
    "idempotency_keys": "user_id = %(uid)s",
    "payment_intents": "user_id = %(uid)s",
    "audit_log": "actor = %(uid)s",
}
# Tables with no user column: nothing of the user's can be left in them by construction.
NO_USER_LINK = frozenset({"templates", "signup_guards", "payment_events", "feature_flags"})


@dataclass
class Seeded:
    user_id: str
    session_id: str
    job_id: str
    # table -> PostgREST eq-filters that select exactly the seeded row(s).
    filters: dict[str, dict[str, str]] = field(default_factory=dict)
    # table -> (column, value) rows that do not go away with the Auth user.
    leftovers: list[tuple[str, str, str]] = field(default_factory=list)


def _ins(conn: Conn, sql: str, params: tuple[object, ...]) -> str:
    return str(scalar(conn, sql, params))


def seed_user_rows(conn: Conn, uid: str) -> Seeded:
    tag = uuid7()
    sid = insert_session(conn, uid)
    job = _ins(
        conn,
        "insert into public.jobs (session_id, user_id, kind) values (%s, %s, 'generate') "
        "returning id::text",
        (sid, uid),
    )
    s = Seeded(user_id=uid, session_id=sid, job_id=job)
    f = s.filters
    f["profiles"] = {"user_id": uid}
    f["cv_sessions"] = {"id": sid}
    f["jobs"] = {"id": job}
    photo = _ins(
        conn,
        "insert into public.photos (user_id, storage_path) values (%s, %s) returning id::text",
        (uid, f"{uid}/photo.png"),
    )
    f["photos"] = {"id": photo}
    mp = _ins(
        conn,
        "insert into public.master_profiles (user_id, name) values (%s, 'm4test') "
        "returning id::text",
        (uid,),
    )
    f["master_profiles"] = {"id": mp}
    ev = _ins(
        conn,
        "insert into public.job_events (job_id, seq, type) values (%s, 1, 'm4test') returning id",
        (job,),
    )
    f["job_events"] = {"id": ev}
    rd = _ins(
        conn,
        "insert into public.renders (session_id, user_id, content_hash) values (%s, %s, %s) "
        "returning id::text",
        (sid, uid, f"m4test-{tag}"),
    )
    f["renders"] = {"id": rd}
    # Credit tables are written only through the functions (app_backend has SELECT only).
    grant(conn, uid, 50, new_key("seed"))
    f["credit_balances"] = {"user_id": uid}
    f["credit_ledger"] = {"user_id": uid}
    res = reserve(conn, uid, sid, 5, new_key("seed-reserve"))
    f["credit_reservations"] = {"id": res}
    tpl = f"m4test_{tag.replace('-', '')}"
    conn.execute(
        "insert into public.templates (id, name, is_active) values (%s, 'm4test', false)", (tpl,)
    )
    f["templates"] = {"id": tpl}
    s.leftovers.append(("templates", "id", tpl))
    llm = _ins(
        conn,
        "insert into public.llm_calls (user_id, step) values (%s, 'm4test') returning id::text",
        (uid,),
    )
    f["llm_calls"] = {"id": llm}
    s.leftovers.append(("llm_calls", "id", llm))
    bucket = f"m4test:{tag}"
    conn.execute(
        "insert into public.signup_guards (bucket, day, count) values (%s, current_date, 1)",
        (bucket,),
    )
    f["signup_guards"] = {"bucket": bucket}
    s.leftovers.append(("signup_guards", "bucket", bucket))
    conn.execute(
        "insert into public.idempotency_keys (user_id, key) values (%s, %s)", (uid, f"m4test-{tag}")
    )
    f["idempotency_keys"] = {"user_id": uid}
    pi = _ins(
        conn,
        "insert into public.payment_intents (user_id, provider, amount_minor, credits) "
        "values (%s, 'm4test', 1, 1) returning id::text",
        (uid,),
    )
    f["payment_intents"] = {"id": pi}
    s.leftovers.append(("payment_intents", "id", pi))
    pe = _ins(
        conn,
        "insert into public.payment_events (provider, event_id) values ('m4test', %s) returning id",
        (f"m4test-{tag}",),
    )
    f["payment_events"] = {"id": pe}
    s.leftovers.append(("payment_events", "id", pe))
    au = _ins(
        conn,
        "insert into public.audit_log (actor, action) values (%s, 'm4test') returning id",
        (uid,),
    )
    f["audit_log"] = {"id": au}
    s.leftovers.append(("audit_log", "id", au))
    flag = f"m4test_{tag}"
    conn.execute("insert into public.feature_flags (key) values (%s)", (flag,))
    f["feature_flags"] = {"key": flag}
    s.leftovers.append(("feature_flags", "key", flag))
    return s


_CLEANABLE = frozenset(
    {
        "templates",
        "llm_calls",
        "signup_guards",
        "payment_intents",
        "payment_events",
        "audit_log",
        "feature_flags",
    }
)
_COLUMNS = frozenset({"id", "bucket", "key"})


def cleanup_leftovers(conn: Conn, seeded: Seeded) -> None:
    for table, col, val in seeded.leftovers:
        assert table in _CLEANABLE and col in _COLUMNS  # fixed identifiers only
        conn.execute(f"delete from public.{table} where {col}::text = %s", (val,))  # noqa: S608


def count_user_rows(conn: Conn, uid: str, job_ids: list[str]) -> dict[str, int]:
    out = {}
    for table, where in USER_LINK.items():
        sql = f"select count(*) from public.{table} where {where}"  # noqa: S608 - fixed text
        out[table] = int(scalar(conn, sql, {"uid": uid, "jobs": job_ids}))
    return out
