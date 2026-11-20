"""Guards: credits and sessions are written only through the repo / SQL functions."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CREDIT_DML = re.compile(
    r"\b(insert\s+into|update|delete\s+from)\s+(?:public\.)?"
    r"(credit_balances|credit_ledger|credit_reservations)\b",
    re.I,
)
SUPABASE_IMPORT = re.compile(r"^\s*(from|import)\s+supabase\b", re.M)
ALLOWED_SUPABASE = (
    "app/adapters/storage/",
    "app/adapters/auth/supabase_admin.py",
)


def _py_files(*folders: str):
    for folder in folders:
        base = ROOT / folder
        if base.exists():
            yield from base.rglob("*.py")


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def test_no_direct_credit_dml_in_app():
    offenders = [
        _rel(p) for p in _py_files("app", "scripts") if CREDIT_DML.search(p.read_text("utf-8"))
    ]
    assert offenders == []


def test_session_writes_only_via_repo():
    pattern = re.compile(r"\.table\(\s*['\"]cv_sessions['\"]")
    offenders = [
        _rel(p) for p in _py_files("app", "scripts") if pattern.search(p.read_text("utf-8"))
    ]
    assert offenders == []
    assert not [p for p in _py_files("app") if ".table(" in p.read_text("utf-8")]


def test_no_service_key_for_db_queries():
    offenders = [
        _rel(p)
        for p in _py_files("app")
        if SUPABASE_IMPORT.search(p.read_text("utf-8")) and not _rel(p).startswith(ALLOWED_SUPABASE)
    ]
    assert offenders == []


def test_render_path_and_storage_writers_use_the_user_root():
    from app.ports.blob_storage import render_path

    uid = "11111111-1111-1111-1111-111111111111"
    assert render_path(uid, "s", "cv").startswith(f"{uid}/")
    writers = [
        _rel(p)
        for p in _py_files("app")
        if re.search(r"\.(put|upload)\(", p.read_text("utf-8"))
        and not _rel(p).startswith("app/adapters/storage/")
    ]
    # Only the finalize service writes blobs today (via render_path); photos, imports and
    # exports writers (M7+) must build paths as f"{user_id}/..." and be added here.
    assert writers == ["app/services/finalize.py"]
