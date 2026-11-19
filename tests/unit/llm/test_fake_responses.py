"""Every canned step response must validate strictly against its step's schema."""

import json
from pathlib import Path

import pytest

from app.adapters.llm.fake import DEFAULT_DIR
from app.domain.cv.cover_letter import CoverLetterStructured
from app.domain.cv.rewrite import RewrittenCV
from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.jd.schemas import JobDescriptionStructured
from app.domain.match.schemas import Eligibility
from app.domain.questions.schemas import GapQuestions

STEP_CASES = {
    "jd_extract": JobDescriptionStructured,
    "eligibility": Eligibility,
    "gap_questions": GapQuestions,
    "rewrite": RewrittenCV,
    "cover_letter": CoverLetterStructured,
    "profile_import": UniversalCVStructured,
}


@pytest.mark.parametrize(("step", "model"), STEP_CASES.items())
def test_step_canned_response_validates_strictly(step, model):
    text = (Path(DEFAULT_DIR) / f"{step}.json").read_text(encoding="utf-8")
    assert model.model_validate_json(text).model_dump(exclude_defaults=True)
    assert set(json.loads(text)) <= set(model.model_fields)


def test_eligibility_has_the_eligible_score():
    text = (Path(DEFAULT_DIR) / "eligibility.json").read_text(encoding="utf-8")
    assert Eligibility.model_validate_json(text).score == 60
