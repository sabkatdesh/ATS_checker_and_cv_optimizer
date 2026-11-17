import pytest
from pydantic import ValidationError

from app.domain.ats.schemas import AtsMatch, SectionScore, compute_ats, non_ats_match
from tests.pipeline.helpers import persona_cv, tech_jd

SECTIONS = {"must_have", "skills", "experience", "tools", "education", "responsibilities"}


def test_compute_ats_on_tech_backend():
    match = compute_ats(tech_jd(), persona_cv("tech_backend"))
    assert match.applies is True
    assert match.score is not None and 0 <= match.score <= 100
    assert set(match.breakdown) == SECTIONS
    assert all(isinstance(s, SectionScore) for s in match.breakdown.values())
    assert match.hard_gaps == match.breakdown["must_have"].missing


def test_non_ats_match_does_not_apply():
    match = non_ats_match()
    assert match.applies is False
    assert match.score is None and match.breakdown == {} and match.hard_gaps == []


def test_score_range_is_enforced():
    with pytest.raises(ValidationError):
        AtsMatch(applies=True, score=101)
