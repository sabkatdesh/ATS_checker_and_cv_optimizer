import app.pipeline.nodes.await_answers as mod
from app.domain.questions.schemas import GapAnswers, GapQuestion
from tests.pipeline.helpers import ctx, deps_for, run

QS = [GapQuestion(id="q1", text="Kubernetes?")]


def test_await_answers_no_questions_skips_interrupt(monkeypatch):
    def boom(value):
        raise AssertionError("interrupt must not be called")

    monkeypatch.setattr(mod, "interrupt", boom)
    _, deps = deps_for({})
    skipped = {"answers": GapAnswers(skipped=True)}
    assert run(mod.await_answers({"questions": []}, deps=deps, ctx=ctx())) == skipped
    assert run(mod.await_answers({}, deps=deps, ctx=ctx())) == skipped


def test_await_answers_interrupts_once_with_questions(monkeypatch):
    seen: list[object] = []

    def fake_interrupt(value):
        seen.append(value)
        return {"answers": {"q1": " I used Kubernetes "}}

    monkeypatch.setattr(mod, "interrupt", fake_interrupt)
    _, deps = deps_for({})
    out = run(mod.await_answers({"questions": QS}, deps=deps, ctx=ctx()))
    assert out == {"answers": GapAnswers(answers={"q1": "I used Kubernetes"})}
    assert len(seen) == 1
    assert seen[0]["type"] == "gap_questions"  # type: ignore[index]
    assert seen[0]["questions"][0]["text"] == "Kubernetes?"  # type: ignore[index]


def test_await_answers_empty_reply_is_skipped(monkeypatch):
    monkeypatch.setattr(mod, "interrupt", lambda value: None)
    _, deps = deps_for({})
    out = run(mod.await_answers({"questions": QS}, deps=deps, ctx=ctx()))
    assert out == {"answers": GapAnswers(skipped=True)}
