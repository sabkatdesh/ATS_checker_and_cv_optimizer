from pydantic import BaseModel


class CoverLetterOptionsRequest(BaseModel):
    tone: str  # "formal" | "conversational"
    length: str  # "short" | "standard"


class CoverLetterEditRequest(BaseModel):
    text: str  # user-edited plain-text cover letter draft
