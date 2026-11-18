import json
from pathlib import Path

import pytest

from app.domain.cv.domain_config import Domain
from app.domain.jd.meta import MAX_META_LENGTH, JdMeta, jd_meta, normalise_jd
from app.domain.jd.schemas import MAX_KEYWORDS, JobDescriptionStructured

CASES = json.loads(
    (Path(__file__).resolve().parents[2] / "fixtures" / "jd" / "meta_cases.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_normalise_jd_cases(case):
    jd = normalise_jd(JobDescriptionStructured.model_validate(case["extracted"]), case["jd_text"])
    for field, want in case["expect"].items():
        got = getattr(jd, field)
        assert (got.isoformat() if hasattr(got, "isoformat") else got) == want


def test_title_and_company_are_capped():
    long_name = "Example " * 40
    jd = JobDescriptionStructured(job_title=long_name, company_name=long_name)
    out = normalise_jd(jd, long_name)
    assert out.job_title is not None and len(out.job_title) <= MAX_META_LENGTH
    assert out.company_name is None or len(out.company_name) <= MAX_META_LENGTH


def test_keywords_keep_the_first_thirty():
    jd = JobDescriptionStructured(keywords=[f"k{i}" for i in range(50)])
    assert jd.keywords == [f"k{i}" for i in range(MAX_KEYWORDS)]


def test_jd_meta_maps_fields():
    jd = JobDescriptionStructured(job_title="Nurse", domain=Domain.MEDICAL, location="Dhaka")
    assert jd_meta(jd) == JdMeta(
        title="Nurse", company=None, domain=Domain.MEDICAL, location="Dhaka"
    )
