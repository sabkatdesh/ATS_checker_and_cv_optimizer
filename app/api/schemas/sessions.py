from pydantic import BaseModel


class StartSessionRequest(BaseModel):
    job_description: str
    cover_letter: bool = False
    cover_letter_tone: str | None = None  # "formal" | "conversational"
    cover_letter_length: str | None = None  # "short" | "standard"


class HITLReplyRequest(BaseModel):
    user_qna: str
