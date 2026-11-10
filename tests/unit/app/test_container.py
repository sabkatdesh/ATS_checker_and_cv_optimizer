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
bad = [m for m in ("database", "core.pipeline.graph", "core.llm_client") if m in sys.modules]
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
    store, auth, pipeline, runner = object(), object(), object(), InlineRunner()
    c = Container(
        AppSettings(_env_file=None),
        store=store,  # type: ignore[arg-type]
        auth=auth,  # type: ignore[arg-type]
        pipeline=pipeline,  # type: ignore[arg-type]
        runner=runner,
        pdf_factory=FakePdfRenderer,
    )
    assert c.store is store
    assert c.auth is auth
    assert c.pipeline is pipeline
    assert c.runner is runner
    assert isinstance(c.make_pdf_renderer(), FakePdfRenderer)


def test_lazy_store_built_once_across_threads(monkeypatch):
    import app.container as mod

    count = 0
    guard = threading.Lock()

    def builder(settings):
        nonlocal count
        with guard:
            count += 1
        return object()

    monkeypatch.setattr(mod, "_default_store", builder)
    c = Container(AppSettings(_env_file=None))
    results: list[object] = []
    threads = [threading.Thread(target=lambda: results.append(c.store)) for _ in range(20)]
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
