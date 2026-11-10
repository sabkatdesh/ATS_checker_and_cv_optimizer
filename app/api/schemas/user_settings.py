from pydantic import BaseModel


class UserSettingsRequest(BaseModel):
    default_template: str | None = None
    accent_color: str | None = None
    bangla_mode: bool | None = None
    cover_letter_default_tone: str | None = None
