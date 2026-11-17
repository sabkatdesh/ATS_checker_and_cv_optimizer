"""Gap questions asked after eligibility and the candidate's answers (completed in Task 4)."""

from pydantic import BaseModel, Field


class GapQuestion(BaseModel):
    id: str
    text: str


class GapQuestions(BaseModel):
    questions: list[GapQuestion] = Field(default_factory=list)


class GapAnswers(BaseModel):
    free_text: str | None = None
