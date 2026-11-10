import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def test_single_seniority_enum():
    from app.domain.cv import universal_cv
    from app.domain.jd import schemas

    assert schemas.SeniorityLevel is universal_cv.SeniorityLevel


def test_profile_text_identical_for_fixture():
    from app.domain.cv.profile_text import ProfileBuilder

    profile = json.loads((FIXTURES / "profile_basic.json").read_text(encoding="utf-8"))
    expected = (FIXTURES / "profile_basic.resume.txt").read_text(encoding="utf-8")
    assert ProfileBuilder.from_profile_dict(profile) == expected


@pytest.mark.parametrize(
    ("module", "name"),
    [
        ("app.domain.cv.universal_cv", "UniversalCVStructured"),
        ("app.domain.jd.schemas", "JobDescriptionStructured"),
        ("app.domain.cv.rewrite", "RewrittenCV"),
    ],
)
def test_json_schema_unchanged(module, name):
    import importlib

    model = getattr(importlib.import_module(module), name)
    snapshot = json.loads((FIXTURES / "schemas" / f"{name}.json").read_text(encoding="utf-8"))
    assert json.loads(json.dumps(model.model_json_schema(), sort_keys=True)) == snapshot
