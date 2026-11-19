from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from app.domain.questions.reply import reply_from_request


class StartSessionRequest(BaseModel):
    job_description: str
    cover_letter: bool = False
    cover_letter_tone: str | None = None  # "formal" | "conversational"
    cover_letter_length: str | None = None  # "short" | "standard"


class HITLReplyRequest(BaseModel):
    user_qna: str | None = None
    answers: dict[str, str] | None = None
    skipped: bool = False

    def to_reply(self) -> Mapping[str, Any] | str | None:
        return reply_from_request(self.user_qna, self.answers, self.skipped)
