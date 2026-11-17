import app.pipeline.nodes.await_answers as mod
from app.domain.questions.schemas import GapAnswers, GapQuestion
from tests.pipeline.helpers import ctx, deps_for, run


def test_await_answers_no_questions_skips_interrupt(monkeypatch):
    def boom(value):
        raise AssertionError("interrupt must not be called")

    monkeypatch.setattr(mod, "interrupt", boom)
    _, deps = deps_for({})
    assert run(mod.await_answers({"questions": []}, deps=deps, ctx=ctx())) == {}
    assert run(mod.await_answers({}, deps=deps, ctx=ctx())) == {}


def test_await_answers_interrupts_with_questions(monkeypatch):
    seen: list[object] = []

    def fake_interrupt(value):
        seen.append(value)
        return "I used Kubernetes"

    monkeypatch.setattr(mod, "interrupt", fake_interrupt)
    _, deps = deps_for({})
    state = {"questions": [GapQuestion(id="q1", text="Kubernetes?")]}
    out = run(mod.await_answers(state, deps=deps, ctx=ctx()))
    assert out == {"answers": GapAnswers(free_text="I used Kubernetes")}
    assert seen == [{"type": "gap_questions", "questions": [{"id": "q1", "text": "Kubernetes?"}]}]


def test_await_answers_none_reply_is_empty_text(monkeypatch):
    monkeypatch.setattr(mod, "interrupt", lambda value: None)
    _, deps = deps_for({})
    state = {"questions": [GapQuestion(id="q1", text="Kubernetes?")]}
    out = run(mod.await_answers(state, deps=deps, ctx=ctx()))
    assert out == {"answers": GapAnswers(free_text="")}
