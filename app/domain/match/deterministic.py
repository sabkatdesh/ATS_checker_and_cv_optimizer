"""Eligibility estimate without the LLM, used when the eligibility reply is unusable."""

from app.domain.ats.schemas import compute_ats
from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.jd.schemas import JobDescriptionStructured
from app.domain.match.schemas import Eligibility

RATIONALE = "Estimated from the job's listed requirements."


def deterministic_eligibility(
    jd: JobDescriptionStructured, cv: UniversalCVStructured
) -> Eligibility:
    ats = compute_ats(jd, cv)
    if jd.requirements.must_have:
        score = round(ats.breakdown["must_have"].score)
    else:
        score = round(ats.score or 0)
    return Eligibility(score=score, rationale=[RATIONALE], gaps=list(ats.hard_gaps))
