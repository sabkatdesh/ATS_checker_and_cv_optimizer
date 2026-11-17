"""Gap questions asked after eligibility and the candidate's answers."""

from typing import Any

from pydantic import BaseModel, Field, field_validator

MAX_QUESTIONS = 5


class GapQuestion(BaseModel):
    id: str
    text: str = Field(min_length=1, max_length=300)
    why: str | None = Field(default=None, max_length=300)
    hint: str | None = Field(default=None, max_length=200)


def _has_text(item: Any) -> bool:
    text = item.get("text") if isinstance(item, dict) else getattr(item, "text", "")
    return not isinstance(text, str) or bool(text.strip())


class GapQuestions(BaseModel):
    questions: list[GapQuestion] = Field(default_factory=list)

    @field_validator("questions", mode="before")
    @classmethod
    def _drop_blank_and_cap(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        return [item for item in value if _has_text(item)][:MAX_QUESTIONS]


class GapAnswers(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    skipped: bool = False
    free_text: str | None = None

    @property
    def is_empty(self) -> bool:
        return self.skipped or (not self.answers and not self.free_text)
