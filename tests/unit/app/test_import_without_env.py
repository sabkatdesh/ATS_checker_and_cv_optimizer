import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_STRIP = re.compile(r"^(AZURE_|SUPABASE_|AUTH__|DB__|REDIS__|SENTRY_DSN$|ENV$)")


def _run(tmp_path, extra: dict[str, str] | None = None):
    env = {k: v for k, v in os.environ.items() if not _STRIP.match(k)}
    env["PYTHONPATH"] = str(ROOT)
    env.update(extra or {})
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", "import app.main; print('ok')"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_import_without_env(tmp_path):
    proc = _run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ok"


def test_bad_env_fails_clearly(tmp_path):
    proc = _run(tmp_path, {"ENV": "production"})
    assert proc.returncode != 0
    assert "Invalid configuration" in proc.stderr
    assert "env" in proc.stderr


_KEEP = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "PATH", "TEMP", "TMP", "COMSPEC", "PATHEXT", "HOME")
_BOOT = (
    "import app.main\n"
    "from fastapi.testclient import TestClient\n"
    "r = TestClient(app.main.app).get('/health')\n"
    "print(r.status_code)\n"
)


def test_boot_without_llm_credentials(tmp_path):
    """A clean environment (no cloud keys, no .env, empty AWS files) still boots and serves."""
    empty = tmp_path / "empty"
    empty.write_text("")
    work = tmp_path / "cwd"
    work.mkdir()
    env = {k: v for k, v in os.environ.items() if k.upper() in _KEEP}
    env.update(
        PYTHONPATH=str(ROOT),
        AWS_CONFIG_FILE=str(empty),
        AWS_SHARED_CREDENTIALS_FILE=str(empty),
        AWS_EC2_METADATA_DISABLED="true",
    )
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _BOOT],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-600:]
    assert proc.stdout.strip().splitlines()[-1] == "200"
