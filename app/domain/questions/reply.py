"""Turn whatever the candidate sent back into GapAnswers; an empty reply means skipped."""

from collections.abc import Mapping, Sequence
from typing import Any

from app.domain.questions.schemas import GapAnswers, GapQuestion

MAX_ANSWER_CHARS = 1000
MAX_FREE_TEXT_CHARS = 6000
_INVISIBLE = " ​﻿"


def _clean(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().strip(_INVISIBLE).strip()[:limit]


def normalise_reply(raw: object, questions: Sequence[GapQuestion]) -> GapAnswers:
    if isinstance(raw, Mapping):
        if raw.get("skipped") is True:
            return GapAnswers(skipped=True)
        given = raw.get("answers")
        free_text = _clean(raw.get("free_text"), MAX_FREE_TEXT_CHARS)
    else:
        given = None
        free_text = _clean(raw, MAX_FREE_TEXT_CHARS)
    known = {q.id for q in questions}
    answers: dict[str, str] = {}
    if isinstance(given, Mapping):
        for qid, value in given.items():
            text = _clean(value, MAX_ANSWER_CHARS)
            if qid in known and text:
                answers[qid] = text
    if not answers and not free_text:
        return GapAnswers(skipped=True)
    return GapAnswers(answers=answers, free_text=free_text or None)


def answers_block(questions: Sequence[GapQuestion], answers: GapAnswers) -> str:
    """The text for the <answers> data block; empty when there is nothing to show."""
    if answers.skipped:
        return ""
    parts = [
        f"Q: {q.text}\nA: {answers.answers[q.id]}" for q in questions if q.id in answers.answers
    ]
    if answers.free_text:
        parts.append(answers.free_text)
    return "\n\n".join(parts)


def reply_from_request(
    user_qna: str | None, answers: Mapping[str, str] | None, skipped: bool
) -> Mapping[str, Any] | str | None:
    """Build the resume value from the API body (the legacy frontend sends user_qna)."""
    if skipped:
        return {"skipped": True}
    if answers:
        return {"answers": dict(answers), "free_text": user_qna}
    return user_qna
