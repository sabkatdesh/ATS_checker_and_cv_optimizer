import pytest
from pydantic import ValidationError

from app.domain.match.schemas import Eligibility


@pytest.mark.parametrize(("raw", "want"), [(0, 0), (100, 100), (72.6, 73), (72.5, 73), (72.4, 72)])
def test_score_is_rounded_half_up(raw, want):
    assert Eligibility(score=raw).score == want


@pytest.mark.parametrize("raw", ["x", -1, 101, 100.6])
def test_score_out_of_range_or_not_a_number_is_invalid(raw):
    with pytest.raises(ValidationError):
        Eligibility(score=raw)


def test_lists_default_empty_and_null_safe():
    e = Eligibility.model_validate({"score": 50, "gaps": None, "blockers": None})
    assert (e.rationale, e.gaps, e.blockers) == ([], [], [])
