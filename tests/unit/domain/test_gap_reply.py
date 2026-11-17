import pytest

from app.domain.questions.reply import answers_block, normalise_reply
from app.domain.questions.schemas import GapAnswers, GapQuestion, GapQuestions

QS = [GapQuestion(id="q1", text="Kubernetes?"), GapQuestion(id="q2", text="Go?")]


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        " \u200b",
        None,
        {"answers": {"q1": "  "}},
        {"skipped": True},
        {"answers": {"zz": "x"}},
        {},
    ],
)
def test_empty_forms_are_skipped(raw):
    out = normalise_reply(raw, QS)
    assert out.skipped is True and out.is_empty


def test_answer_is_stripped():
    out = normalise_reply({"answers": {"q1": " 5 years ", "zz": "x", "q2": "\u00a0"}}, QS)
    assert out == GapAnswers(answers={"q1": "5 years"})
    assert not out.is_empty


def test_answer_is_capped_at_1000():
    out = normalise_reply({"answers": {"q1": "a" * 5000}}, QS)
    assert len(out.answers["q1"]) == 1000


def test_string_reply_becomes_free_text():
    assert normalise_reply(" Q1: x\nA1: y ", QS) == GapAnswers(free_text="Q1: x\nA1: y")


def test_skipped_flag_wins_over_answers():
    assert normalise_reply({"skipped": True, "answers": {"q1": "x"}}, QS).skipped is True


def test_answers_block_pairs_question_and_answer():
    answers = GapAnswers(answers={"q2": "two years"})
    assert answers_block(QS, answers) == "Q: Go?\nA: two years"
    assert answers_block(QS, GapAnswers(skipped=True)) == ""


def test_seven_questions_keep_the_first_five():
    items = [{"id": f"q{i}", "text": f"t{i}"} for i in range(7)]
    assert [q.text for q in GapQuestions.model_validate({"questions": items}).questions] == [
        f"t{i}" for i in range(5)
    ]


def test_blank_question_text_is_dropped():
    raw = {"questions": [{"id": "a", "text": "  "}, {"id": "b", "text": "Real?"}]}
    assert [q.id for q in GapQuestions.model_validate(raw).questions] == ["b"]
