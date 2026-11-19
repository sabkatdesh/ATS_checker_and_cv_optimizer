"""What a profile needs before generation may start (spec 08 H1)."""

from typing import Literal

from app.domain.cv.universal_cv import UniversalCVStructured

MinimumGap = Literal["NAME", "CONTACT", "EXPERIENCE_OR_EDUCATION"]


def check_minimums(cv: UniversalCVStructured) -> list[MinimumGap]:
    """A name, one contact (email or phone) and at least one job or education entry."""
    gaps: list[MinimumGap] = []
    if not cv.meta.full_name:
        gaps.append("NAME")
    if not (cv.meta.email or cv.meta.phone):
        gaps.append("CONTACT")
    if not (cv.work_experience or cv.education):
        gaps.append("EXPERIENCE_OR_EDUCATION")
    return gaps
