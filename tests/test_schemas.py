"""
test_schemas.py — Parse all test CV texts through UniversalCVStructured.
Assert no crashes and required fields are populated.
"""
import json
import pytest
from pathlib import Path

from core.schemas.universal_cv import UniversalCVStructured
from tests.conftest import TEST_SET_DIR, ALL_TEST_PAIRS


def _cv_text_from_pair(data: dict) -> str:
    """Extract cv_text field or skip if missing."""
    if "cv_text" not in data:
        pytest.skip("Test pair missing 'cv_text' field")
    return data["cv_text"]


@pytest.mark.parametrize("name", ALL_TEST_PAIRS)
def test_schema_parses_without_crash(name):
    """UniversalCVStructured.model_validate(dict) must not raise for any test pair."""
    path = TEST_SET_DIR / f"{name}.json"
    if not path.exists():
        pytest.skip(f"Test data not found: {path}")

    with open(path) as f:
        data = json.load(f)

    raw = data.get("structured_cv") or data
    cv = UniversalCVStructured.model_validate(raw)

    assert cv is not None


@pytest.mark.parametrize("name", ALL_TEST_PAIRS)
def test_schema_null_lists_coerced(name):
    """None values on list fields must be coerced to [] (NullSafeListMixin)."""
    path = TEST_SET_DIR / f"{name}.json"
    if not path.exists():
        pytest.skip(f"Test data not found: {path}")

    with open(path) as f:
        data = json.load(f)

    raw = data.get("structured_cv") or data
    # Inject None values into all list-like keys to test the mixin
    nulled = {k: None if isinstance(v, list) else v for k, v in raw.items()}
    cv = UniversalCVStructured.model_validate(nulled)

    assert isinstance(cv.work_experience, list)
    assert isinstance(cv.education, list)
    assert isinstance(cv.certifications, list)
