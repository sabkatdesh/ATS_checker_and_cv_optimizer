"""
Pydantic models for structured cover letter output.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CoverLetterStructured(BaseModel):
    salutation: str = Field(
        default="Dear Hiring Manager,",
        description="Opening salutation. Uses hiring manager name if found in JD.",
    )
    opening_paragraph: str = Field(
        default="",
        description=(
            "Hook opening — references the specific role and one headline achievement. "
            "No generic 'I am writing to apply' opener."
        ),
    )
    body_paragraphs: list[str] = Field(
        default_factory=list,
        description=(
            "Each paragraph links ONE specific CV achievement to ONE JD requirement. "
            "Only write paragraphs where real evidence exists. Never invent."
        ),
    )
    closing_paragraph: str = Field(
        default="",
        description="Brief closing that reiterates fit and invites next step.",
    )
    sign_off: str = Field(
        default="Sincerely,",
        description="Sign-off line (e.g. 'Sincerely,' or 'Best regards,').",
    )
