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
