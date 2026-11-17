"""
test_schemas.py — Parse all test CV texts through UniversalCVStructured.
Assert no crashes and required fields are populated.
"""

import json

import pytest

from app.domain.cv.universal_cv import UniversalCVStructured
from tests.conftest import ALL_TEST_PAIRS, TEST_SET_DIR


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


# ── RewrittenCV keeps every UniversalCV section (E2) ──────────────────────────


def test_rewritten_cv_is_a_universal_cv_with_a_change_log():
    from app.domain.cv.rewrite import ChangeLogEntry, RewrittenCV

    assert issubclass(RewrittenCV, UniversalCVStructured)
    assert set(UniversalCVStructured.model_fields) < set(RewrittenCV.model_fields)
    cv = RewrittenCV.model_validate(
        {
            "domain": "medical",
            "certifications": [{"name": f"Cert {i}"} for i in range(8)],
            "change_log": [{"section": "projects", "entry_id": "p3", "reason": "Not relevant"}],
            "gaps_unaddressed": None,
        }
    )
    assert cv.domain.value == "medical" and len(cv.certifications) == 8
    assert cv.change_log == [
        ChangeLogEntry(
            section="projects", entry_id="p3", before=None, after=None, reason="Not relevant"
        )
    ]
    assert cv.gaps_unaddressed == []


@pytest.mark.parametrize(
    "entry",
    [
        {"section": "not_a_section", "reason": "x"},
        {"section": "projects"},
    ],
)
def test_change_log_entry_limits(entry):
    from pydantic import ValidationError

    from app.domain.cv.rewrite import ChangeLogEntry

    with pytest.raises(ValidationError):
        ChangeLogEntry.model_validate(entry)


def test_rewrite_entry_models_are_gone():
    import app.domain.cv.rewrite as rewrite

    assert not [n for n in dir(rewrite) if n.startswith("Rewrite") and n != "RewrittenCV"]


def test_change_log_text_is_truncated_not_rejected():
    from app.domain.cv.rewrite import ChangeLogEntry

    entry = ChangeLogEntry.model_validate(
        {"section": "projects", "before": "b" * 500, "after": "a" * 201, "reason": "r" * 300}
    )
    assert entry.before == "b" * 200 and entry.after == "a" * 200 and entry.reason == "r" * 200
