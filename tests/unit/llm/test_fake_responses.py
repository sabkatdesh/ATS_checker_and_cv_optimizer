"""Every canned legacy response must pass the parser the legacy pipeline uses for that chain."""

import json
from pathlib import Path

import pytest

from app.adapters.llm.fake import DEFAULT_DIR
from app.domain.cv.cover_letter import CoverLetterStructured
from app.domain.cv.rewrite import RewrittenCV
from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.jd.schemas import JobDescriptionStructured, SummaryJD
from app.domain.match.schemas import Match, SummaryCV
from app.domain.parsing.safe_parser import safe_llm_parse

CASES = {
    "quick_jd": SummaryJD,
    "quick_cv": SummaryCV,
    "verdict": Match,
    "detailed_jd": JobDescriptionStructured,
    "detailed_cv": UniversalCVStructured,
    "rewrite": RewrittenCV,
    "cover_letter": CoverLetterStructured,
    "profile_import": UniversalCVStructured,
}


def _text(chain: str) -> str:
    return (Path(DEFAULT_DIR) / f"legacy.{chain}.json").read_text(encoding="utf-8")


@pytest.mark.parametrize(("chain", "model"), CASES.items())
def test_canned_response_validates_strictly(chain, model):
    parsed = model.model_validate_json(_text(chain))
    assert parsed.model_dump(exclude_defaults=True), "canned response must carry real content"
    assert set(json.loads(_text(chain))) <= set(model.model_fields)


@pytest.mark.parametrize(("chain", "model"), CASES.items())
def test_canned_response_passes_legacy_parser_without_fallback(chain, model):
    fallback = model.model_construct()
    assert safe_llm_parse(_text(chain), model, fallback) is not fallback


def test_verdict_has_the_eligible_score():
    assert Match.model_validate_json(_text("verdict")).score == 60
