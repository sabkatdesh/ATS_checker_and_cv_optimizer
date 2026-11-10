from pathlib import Path

from scripts.check_file_length import TEMPORARY_ALLOW_LIST, check


def _write(root: Path, rel: str, lines: int) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n" * lines, encoding="utf-8")
    return path


def test_app_file_over_300_is_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "app/x.py", 301)
    errors, warnings = check([Path("app/x.py")])
    assert len(errors) == 1
    assert "app/x.py" in errors[0].replace("\\", "/")
    assert warnings == []


def test_app_file_at_300_ok(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "app/x.py", 300)
    assert check([Path("app/x.py")]) == ([], [])


def test_test_file_301_is_warning_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "tests/test_x.py", 301)
    errors, warnings = check([Path("tests/test_x.py")])
    assert errors == []
    assert len(warnings) == 1


def test_test_file_401_is_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "tests/test_x.py", 401)
    errors, _ = check([Path("tests/test_x.py")])
    assert len(errors) == 1


def test_allow_list_is_empty():
    assert TEMPORARY_ALLOW_LIST == frozenset()
