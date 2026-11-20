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
