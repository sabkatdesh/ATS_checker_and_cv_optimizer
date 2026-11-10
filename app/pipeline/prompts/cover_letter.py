"""Cover letter prompt."""

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate

from app.domain.cv.cover_letter import CoverLetterStructured

parser_cover_letter: PydanticOutputParser[CoverLetterStructured] = PydanticOutputParser(
    pydantic_object=CoverLetterStructured
)


# ── Cover Letter prompt ─────────────────────────────────────────────────────────

COVER_LETTER_PROMPT = PromptTemplate(
    template="""\
You are an expert cover letter writer. Write a cover letter for the candidate below.

STRICT RULES — follow every rule or the output is unusable:
1. NEVER invent achievements, skills, or claims not present in the CV or tailored CV.
2. Every body paragraph must cite ONE specific achievement from the CV and link it to ONE requirement from the JD.
3. Requirements with no supporting CV evidence are silently skipped — do NOT mention them.
4. Salutation: use the hiring manager's name if detectable in the JD, otherwise "Dear Hiring Manager,".
5. No generic opener like "I am writing to apply for...". Open with a hook tied to the role.
6. Tone: {tone}. Length: {length} (~{word_target} words total body).
7. Sign-off: "Sincerely," for formal tone; "Best regards," for conversational.

CANDIDATE CV (tailored/rewritten):
{cv_text}

JOB DESCRIPTION:
{jd_text}

GAPS (evidence missing — do NOT fill these by invention):
{gaps}

{format_instructions}
""",
    input_variables=["tone", "length", "word_target", "cv_text", "jd_text", "gaps"],
    partial_variables={"format_instructions": parser_cover_letter.get_format_instructions()},
)
