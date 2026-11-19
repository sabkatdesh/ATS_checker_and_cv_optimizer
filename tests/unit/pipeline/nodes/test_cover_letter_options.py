import app.pipeline.nodes.cover_letter_options as mod
from app.pipeline.nodes.cover_letter_options import route_cover_letter
from app.pipeline.state import RunOptions
from tests.pipeline.helpers import ctx, deps_for, run


def _no_interrupt(monkeypatch):
    def boom(value):
        raise AssertionError("interrupt must not be called")

    monkeypatch.setattr(mod, "interrupt", boom)


def _call(state: dict) -> dict:
    _, deps = deps_for({})
    return run(mod.cover_letter_options(state, deps=deps, ctx=ctx()))


def test_cover_letter_options_not_requested_is_noop(monkeypatch):
    _no_interrupt(monkeypatch)
    assert _call({"options": RunOptions()}) == {}


def test_cover_letter_options_already_set_is_noop(monkeypatch):
    _no_interrupt(monkeypatch)
    opts = RunOptions(cover_letter=True, cover_letter_tone="formal", cover_letter_length="short")
    assert _call({"options": opts}) == {}


def test_cover_letter_options_interrupts_and_applies_reply(monkeypatch):
    seen: list[object] = []

    def fake_interrupt(value):
        seen.append(value)
        return {"tone": "conversational", "length": "standard"}

    monkeypatch.setattr(mod, "interrupt", fake_interrupt)
    out = _call({"options": RunOptions(cover_letter=True, max_passes=3)})
    assert seen == [{"type": "cover_letter_options"}]
    assert out == {
        "options": RunOptions(
            cover_letter=True,
            cover_letter_tone="conversational",
            cover_letter_length="standard",
            max_passes=3,
        )
    }


def test_cover_letter_options_bad_reply_falls_back_to_defaults(monkeypatch):
    monkeypatch.setattr(mod, "interrupt", lambda value: {"tone": "shouty", "length": 7})
    out = _call({"options": RunOptions(cover_letter=True)})
    assert out["options"].cover_letter_tone == "formal"
    assert out["options"].cover_letter_length == "standard"


def test_cover_letter_options_route():
    full = RunOptions(cover_letter=True, cover_letter_tone="formal", cover_letter_length="short")
    assert route_cover_letter({"options": full}) == "generate"
    assert route_cover_letter({"options": RunOptions()}) == "skip"
    assert route_cover_letter({"options": RunOptions(cover_letter=True)}) == "skip"
    assert route_cover_letter({}) == "skip"
