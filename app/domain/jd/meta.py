"""Clean the job title, company, deadline and contact the model extracted from a job description.

The model may invent a company or an email, so both are kept only when the job text contains them.
"""

import re
from datetime import date

from pydantic import BaseModel

from app.domain.cv.domain_config import Domain
from app.domain.jd.schemas import JobDescriptionStructured

MAX_META_LENGTH = 120
_MIN_DEADLINE_YEAR = 2000
_PLACEHOLDERS = frozenset(
    {"not specified", "n/a", "na", "unknown", "none", "-", "not mentioned", "confidential"}
)
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s.]+")
_NON_WORD = re.compile(r"[\W_]+")


class JdMeta(BaseModel, frozen=True):
    title: str | None = None
    company: str | None = None
    domain: Domain = Domain.GENERAL
    location: str | None = None
    deadline: date | None = None
    application_email: str | None = None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = " ".join(value.split())
    if not text or text.casefold().rstrip(".") in _PLACEHOLDERS:
        return None
    return text[:MAX_META_LENGTH].strip()


def _words(text: str) -> str:
    return " " + _NON_WORD.sub(" ", text.casefold()).strip() + " "


def _company_in_text(company: str | None, source_text: str) -> str | None:
    if company is None:
        return None
    needle = _words(company)
    return company if needle.strip() and needle in _words(source_text) else None


def _email_in_text(email: str | None, source_text: str) -> str | None:
    if email is None:
        return None
    address = email.strip()
    if _EMAIL.fullmatch(address) and address.casefold() in source_text.casefold():
        return address
    return None


def normalise_jd(jd: JobDescriptionStructured, source_text: str) -> JobDescriptionStructured:
    deadline = jd.deadline if jd.deadline and jd.deadline.year >= _MIN_DEADLINE_YEAR else None
    return jd.model_copy(
        update={
            "job_title": _clean(jd.job_title),
            "company_name": _company_in_text(_clean(jd.company_name), source_text),
            "location": _clean(jd.location),
            "deadline": deadline,
            "application_email": _email_in_text(_clean(jd.application_email), source_text),
        }
    )


def jd_meta(jd: JobDescriptionStructured) -> JdMeta:
    return JdMeta(
        title=jd.job_title,
        company=jd.company_name,
        domain=jd.domain,
        location=jd.location,
        deadline=jd.deadline,
        application_email=jd.application_email,
    )
