import threading

from app.pipeline.hooks import NoopHooks
from app.pipeline.runs import RunRegistry


class _Hooks(NoopHooks):
    pass


def test_cancel_unknown_id_returns_false():
    assert RunRegistry().cancel("nope") is False


def test_open_cancel_then_get_sees_cancelled():
    runs = RunRegistry()
    ctx = runs.open("s1")
    assert ctx.session_id == "s1" and not ctx.cancel.is_cancelled
    assert runs.cancel("s1") is True
    assert runs.get("s1").cancel.is_cancelled


def test_open_keeps_the_given_hooks():
    hooks = _Hooks()
    runs = RunRegistry()
    runs.open("s1", hooks)
    assert runs.get("s1").hooks is hooks


def test_get_absent_returns_a_default_context_with_noop_hooks():
    runs = RunRegistry()
    ctx = runs.get("s9")
    assert ctx.session_id == "s9" and isinstance(ctx.hooks, NoopHooks)
    assert not ctx.cancel.is_cancelled


def test_close_forgets_the_run():
    runs = RunRegistry()
    runs.open("s1")
    runs.close("s1")
    assert runs.cancel("s1") is False
    runs.close("s1")  # closing twice is harmless


def test_open_reuses_a_context_cancelled_while_paused():
    runs = RunRegistry()
    runs.open("s1")
    runs.cancel("s1")
    assert runs.open("s1").cancel.is_cancelled


def test_thread_safety_smoke():
    runs = RunRegistry()
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            for j in range(200):
                sid = f"s{i}-{j}"
                runs.open(sid)
                assert runs.cancel(sid) is True
                assert runs.get(sid).cancel.is_cancelled
                runs.close(sid)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
