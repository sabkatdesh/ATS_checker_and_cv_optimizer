import subprocess
import sys
import threading
from pathlib import Path

from app.adapters.background.inline_runner import InlineRunner
from app.config.settings import AppSettings
from app.container import Container
from tests.fakes.fake_renderers import FakePdfRenderer

ROOT = Path(__file__).resolve().parents[3]

_SCRIPT = """
import sys
from app.config.settings import AppSettings
from app.container import build_container
build_container(AppSettings(_env_file=None))
bad = [m for m in ("api", "database", "core", "services") if m in sys.modules]
print(",".join(bad))
sys.exit(1 if bad else 0)
"""


def test_build_container_imports_nothing_legacy(tmp_path):
    env = {
        "PATH": "",
        "PYTHONPATH": str(ROOT),
        "SYSTEMROOT": r"C:\Windows",
    }
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", _SCRIPT],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_overrides_are_used():
    storage, auth, pipeline, runner = object(), object(), object(), InlineRunner()
    c = Container(
        AppSettings(_env_file=None),
        storage=storage,  # type: ignore[arg-type]
        auth=auth,  # type: ignore[arg-type]
        pipeline=pipeline,  # type: ignore[arg-type]
        runner=runner,
        pdf_factory=FakePdfRenderer,
    )
    assert c.storage is storage
    assert c.auth is auth
    assert c.pipeline is pipeline
    assert c.runner is runner
    assert isinstance(c.make_pdf_renderer(), FakePdfRenderer)


def test_lazy_storage_built_once_across_threads(monkeypatch):
    import app.container as mod

    count = 0
    guard = threading.Lock()

    def builder(settings, supabase):
        nonlocal count
        with guard:
            count += 1
        return object()

    monkeypatch.setattr(mod, "_default_storage", builder)
    c = Container(AppSettings(_env_file=None))
    results: list[object] = []
    threads = [threading.Thread(target=lambda: results.append(c.storage)) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert count == 1
    assert len({id(r) for r in results}) == 1


def test_make_pdf_renderer_returns_new_instance_each_call():
    c = Container(AppSettings(_env_file=None), pdf_factory=FakePdfRenderer)
    assert c.make_pdf_renderer() is not c.make_pdf_renderer()


def test_inline_runner_runs_synchronously():
    ran: list[int] = []
    InlineRunner().submit(lambda: ran.append(1))
    assert ran == [1]


def test_builder_reading_another_property_does_not_deadlock(monkeypatch):
    import app.container as mod

    c = Container(AppSettings(_env_file=None), storage=object())  # type: ignore[arg-type]
    seen: list[object] = []

    def pipeline_builder(settings, gateway, prompts):
        seen.append(c.storage)
        return object()

    monkeypatch.setattr(mod, "_default_pipeline", pipeline_builder)
    t = threading.Thread(target=lambda: c.pipeline, daemon=True)
    t.start()
    t.join(timeout=5)
    assert not t.is_alive()
    assert len(seen) == 1


def test_missing_supabase_config_fails_on_first_use_not_build(monkeypatch):
    import pytest

    from app.config.settings import ConfigError
    from app.container import build_container

    for name in (
        "SUPABASE_URL",
        "SUPABASE_SECRET_KEY",
        "SUPABASE_SERVICE_KEY",
        "AUTH__SUPABASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    c = build_container(AppSettings(_env_file=None))
    with pytest.raises(ConfigError, match="Database access needs AUTH__SUPABASE_URL"):
        _ = c.storage
    with pytest.raises(ConfigError, match="AUTH__JWKS_URL"):
        _ = c.auth


def test_storage_and_auth_share_one_supabase_client(monkeypatch):
    import app.container as mod

    made: list[object] = []

    def fake_make(url, key):
        made.append(object())
        return made[-1]

    monkeypatch.setattr(mod, "make_supabase_client", fake_make)
    c = Container(
        AppSettings(
            _env_file=None, auth={"supabase_url": "https://x.supabase.co"}, supabase_secret_key="k"
        )
    )
    assert c.storage is not None and c.auth is not None
    assert len(made) == 1


class _ClosablePool:
    def __init__(self) -> None:
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


def test_close_closes_an_opened_pool_once():
    pool = _ClosablePool()
    c = Container(AppSettings(_env_file=None), pool=pool)  # type: ignore[arg-type]
    c.close()
    c.close()
    assert pool.closed == 1


def test_close_without_a_pool_does_not_open_one():
    c = Container(AppSettings(_env_file=None))
    c.close()  # no DB__DSN: must not raise ConfigError
    assert c._pool is None


def test_app_lifespan_closes_the_container():
    from fastapi.testclient import TestClient

    from app.main import create_app

    pool = _ClosablePool()
    c = Container(AppSettings(_env_file=None, env="test"), pool=pool)  # type: ignore[arg-type]
    with TestClient(create_app(c)):
        assert pool.closed == 0
    assert pool.closed == 1


def test_pool_access_after_close_raises_instead_of_reopening():
    import pytest

    from app.adapters.db.errors import DbUnavailable

    pool = _ClosablePool()
    c = Container(AppSettings(_env_file=None), pool=pool)  # type: ignore[arg-type]
    c.close()
    with pytest.raises(DbUnavailable):
        _ = c.pool
    assert pool.closed == 1
