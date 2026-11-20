"""Skip-by-default gate and preflight for the remote suite (pure; unit-tested offline)."""

import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from tests.remote._env import PAUSED_MESSAGE, SKIP_REASON, RemoteEnv

REMOTE_DIR = Path(__file__).resolve().parent


def is_remote_item(item: Any, remote_dir: Path = REMOTE_DIR) -> bool:
    path = Path(str(getattr(item, "path", "") or getattr(item, "fspath", "")))
    return remote_dir in path.parents


def mark_remote_items(items: list[Any], enabled: bool, remote_dir: Path = REMOTE_DIR) -> int:
    """Mark every item under tests/remote as `remote`; skip them unless enabled. Returns the
    number skipped. (A sub-directory conftest hook still sees the whole session's items.)"""
    skipped = 0
    for item in items:
        if not is_remote_item(item, remote_dir):
            continue
        item.add_marker(pytest.mark.remote)
        if not enabled:
            item.add_marker(pytest.mark.skip(reason=SKIP_REASON))
            skipped += 1
    return skipped


# ─── Target safety: dev project only, app_backend role only ──────────────────────

# cv-optimizer-dev. The suite refuses any other project; override only via M4_PROJECT_REF.
DEV_PROJECT_REF = "iugoabvedjwvusuldeil"
PROJECT_REF_VAR = "M4_PROJECT_REF"
PROJECT_MESSAGE = (
    "remote suite runs only against the dev project (M4_PROJECT_REF) — refusing to run"
)
EXPECTED_ROLE = "app_backend"
ROLE_MESSAGE = "DB__DSN must be the app_backend role — refusing to run"

# current_user is the bare role even through Supavisor (user `app_backend.<project-ref>`).
ROLE_SQL = """
select current_user::text as role, session_user::text as session_role, r.rolsuper as is_super,
       exists (
         select 1 from pg_class c join pg_namespace n on n.oid = c.relnamespace
         where n.nspname in ('public', 'lg') and c.relowner = r.oid
       ) as owns_tables
from pg_roles r where r.rolname = current_user
"""


class UnsafeTarget(Exception):
    """The configured target is not the dev project's app_backend role."""


def project_ref(environ: dict[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    return env.get(PROJECT_REF_VAR, "").strip() or DEV_PROJECT_REF


def project_problem(env: RemoteEnv, ref: str) -> str | None:
    """Which setting points elsewhere ('url' / 'dsn'), else None. Never returns values."""
    host = (urlparse(env.supabase_url).hostname or "").lower()
    if not ref or ref not in host:
        return "url"
    try:
        info = conninfo_to_dict(env.db_dsn.get_secret_value())
    except psycopg.ProgrammingError:
        return "dsn"
    if ref not in str(info.get("user", "")) and ref not in str(info.get("host", "")):
        return "dsn"
    return None


def role_problem(row: Mapping[str, Any] | None) -> str | None:
    """Why the connected role is unsafe for this suite, else None."""
    if not row:
        return "role not found"
    if row.get("role") != EXPECTED_ROLE or row.get("session_role") != EXPECTED_ROLE:
        return "not app_backend"
    if row.get("is_super"):
        return "superuser"
    if row.get("owns_tables"):
        return "owns tables (grants would not bind it)"
    return None


def check_backend_role(conn: Any) -> None:
    """Raise UnsafeTarget unless conn is app_backend: not superuser, owning no table."""
    row = conn.execute(ROLE_SQL).fetchone()
    problem = role_problem(row)
    if problem:
        err = UnsafeTarget(ROLE_MESSAGE)
        # role names and a fixed label only: never a DSN, password or key
        names = f"current={row.get('role')}, session={row.get('session_role')}" if row else ""
        err.reason = f"{problem}; {names}" if names else problem  # type: ignore[attr-defined]
        raise err


def preflight(
    enabled: bool,
    load: Callable[[], RemoteEnv],
    probe: Callable[[RemoteEnv], None],
    ref: str = DEV_PROJECT_REF,
) -> RemoteEnv | None:
    """None when disabled (nothing is loaded or probed); else the env, or pytest.exit.

    Order: env present -> both URL and DSN point at the dev project -> 5 s connect, and the
    role is app_backend (probe raises UnsafeTarget otherwise)."""
    if not enabled:
        return None
    try:
        env = load()
    except RuntimeError as exc:
        pytest.exit(str(exc), returncode=2)
    if project_problem(env, ref):
        pytest.exit(PROJECT_MESSAGE, returncode=2)
    try:
        probe(env)
    except UnsafeTarget as exc:
        reason = getattr(exc, "reason", "")
        pytest.exit(f"{ROLE_MESSAGE} ({reason})" if reason else ROLE_MESSAGE, returncode=2)
    except (psycopg.OperationalError, httpx.TransportError, TimeoutError, OSError):
        pytest.exit(PAUSED_MESSAGE, returncode=2)
    return env
