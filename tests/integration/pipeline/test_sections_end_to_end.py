"""Whatever the rewrite drops, the final tailored CV keeps every source section (D2, E3)."""

from typing import Any

import pytest

from app.domain.cv.rewrite import RewrittenCV
from app.domain.cv.sections import PROTECTED_SECTIONS, SECTIONS, present_sections
from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.match.schemas import Eligibility
from app.domain.trust.judge import JudgeFindings
from app.pipeline.checkpoint_types import new_checkpointer
from app.pipeline.graph import build_graph
from app.pipeline.service import PipelineService
from app.pipeline.state import RunOptions
from tests.pipeline.helpers import deps_for, persona_cv, persona_jd_text, tech_jd

PERSONAS = (
    "tech_backend",
    "nurse_icu",
    "electrician_trades",
    "teacher_volunteer",
    "banker_mixed_bn",
    "fresh_graduate_sparse",
)
_LIST_SECTIONS = [s for s in SECTIONS if s not in ("meta", "references_available")]


def _lossy_rewrite(source: UniversalCVStructured) -> RewrittenCV:
    """Drop the last present section and the last entry of every protected list."""
    data: dict[str, Any] = source.model_dump()
    dropped = [s for s in _LIST_SECTIONS if s in present_sections(source)][-1]
    data.pop(dropped)
    for name in PROTECTED_SECTIONS:
        if len(data.get(name) or []) >= 2:
            data[name] = data[name][:-1]
    return RewrittenCV.model_validate(data)


def _final(name: str) -> tuple[UniversalCVStructured, RewrittenCV, list[str]]:
    source = persona_cv(name)
    jd = tech_jd().model_copy(update={"domain": source.domain})
    _, deps = deps_for(
        {
            "jd_extract": [jd],
            "cv_extract": [source],
            "eligibility": [Eligibility(score=70)],
            "rewrite": [_lossy_rewrite(source) for _ in range(3)],
            "verify_claims": [JudgeFindings()],
        }
    )
    svc = PipelineService(build_graph(deps, new_checkpointer()), deps.runs)
    final = svc.run(
        job_description=persona_jd_text(name),
        user_resume_text="cv text",
        thread_id="t1",
        options=RunOptions(),
    )
    return source, final["tailored_cv"], [w.code for w in final["warnings"]]


def _keys(cv: UniversalCVStructured, name: str) -> list[str]:
    return [entry.model_dump_json() for entry in getattr(cv, name)]


@pytest.mark.parametrize("name", PERSONAS)
def test_every_source_section_survives_the_rewrite(name):
    source, output, warnings = _final(name)
    assert present_sections(source) <= present_sections(output)
    assert "SECTION_RESTORED" in warnings


@pytest.mark.parametrize("name", ["nurse_icu", "electrician_trades"])
def test_every_protected_entry_survives_the_rewrite(name):
    source, output, _ = _final(name)
    for section in PROTECTED_SECTIONS:
        assert sorted(_keys(source, section)) == sorted(_keys(output, section))
