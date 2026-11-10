import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LEGACY_IMPORT = re.compile(r"^\s*(from|import) (core|services|database|api)\b", re.M)


def test_legacy_paths_gone():
    for name in ("api.py", "database.py", "core", "services"):
        assert not (ROOT / name).exists(), name


def test_no_legacy_imports():
    offenders = []
    for folder in ("app", "tests", "scripts"):
        for path in (ROOT / folder).rglob("*.py"):
            if path.name == "test_no_legacy.py":
                continue
            if LEGACY_IMPORT.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_no_print_in_app():
    offenders = [
        str(p.relative_to(ROOT))
        for p in (ROOT / "app").rglob("*.py")
        if re.search(r"(?<![\w.])print\(", p.read_text(encoding="utf-8"))
    ]
    assert offenders == []
