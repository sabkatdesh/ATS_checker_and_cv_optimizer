from datetime import date, datetime

import pytest

from app.domain.cv.profile_dates import parse_profile_date


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (date(2021, 3, 15), date(2021, 3, 15)),
        (datetime(2021, 3, 15, 10, 30), date(2021, 3, 15)),
        ("2021-03-15", date(2021, 3, 15)),
        ("2021-03", date(2021, 3, 1)),
        ("2021", date(2021, 1, 1)),
        ("Mar 2021", date(2021, 3, 1)),
        ("Sept 2021", date(2021, 9, 1)),
        ("March 2021", date(2021, 3, 1)),
        ("  march 2021 ", date(2021, 3, 1)),
        ("২০১৯-০৫", date(2019, 5, 1)),
        ("২০১৯-০৫-২০", date(2019, 5, 20)),
    ],
)
def test_accepted_forms(value, expected):
    assert parse_profile_date(value) == expected


@pytest.mark.parametrize("value", ["Present", "present", "Current", "", "   ", None])
def test_open_ended_or_empty_is_none(value):
    assert parse_profile_date(value) is None


@pytest.mark.parametrize(
    "value", ["garbage", "2021-13", "2021-02-30", "Smarch 2021", "21", 2021, ["2021"], "0000"]
)
def test_garbage_is_none(value):
    assert parse_profile_date(value) is None
