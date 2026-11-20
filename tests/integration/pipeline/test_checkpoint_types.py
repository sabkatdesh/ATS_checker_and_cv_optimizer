"""Every state type round-trips the checkpointer without a langgraph serde warning."""

import logging

import pytest
from langgraph.checkpoint.serde import jsonplus

from app.adapters.llm.fake import DEFAULT_DIR
from app.domain.cv.cover_letter import CoverLetterStructured
from app.domain.cv.rewrite import RewrittenCV
from app.domain.match.schemas import Eligibility
from app.domain.questions.schemas import GapQuestion, GapQuestions
from app.domain.trust.judge import JudgeFindings
from app.pipeline.checkpoint_types import allowed_modules
from app.pipeline.checkpointer import MemoryCheckpointerFactory
from app.pipeline.graph import build_state_graph
from app.pipeline.service import PipelineService
from app.pipeline.state import RunOptions
from tests.pipeline.helpers import (
    deps_for,
    persona_answers,
    persona_cv,
    persona_jd_text,
    persona_profile,
    tech_jd,
)

SERDE_LOGGER = "langgraph.checkpoint.serde.jsonplus"


def test_allowlist_covers_nested_models_and_enums():
    names = {name for _, name in allowed_modules()}
    assert {"Domain", "SeniorityLevel", "EmploymentType", "SectionScore", "ChangeLogEntry"} <= names
    assert {"WorkExperienceEntry", "PipelineWarning", "RunOptions"} <= names
    assert {"TrustReport", "UnsupportedClaim", "SourceCounts"} <= names


def test_interrupt_resume_flow_logs_nothing_from_the_serde(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(jsonplus, "_warned_unregistered_types", set())  # warnings fire once each
    letter = CoverLetterStructured.model_validate_json(
        (DEFAULT_DIR / "cover_letter.json").read_text("utf-8")
    )
    source = persona_cv()
    lossy = source.model_dump(exclude={"education"})
    _, deps = deps_for(
        {
            "jd_extract": [tech_jd()],
            "eligibility": [Eligibility(score=60, gaps=["Kubernetes"])],
            "gap_questions": [GapQuestions(questions=[GapQuestion(id="q1", text="Kubernetes?")])],
            "rewrite": [RewrittenCV.model_validate(lossy) for _ in range(3)],
            "verify_claims": [JudgeFindings()],
            "cover_letter": [letter],
        }
    )
    svc = PipelineService(build_state_graph(deps), deps.runs, MemoryCheckpointerFactory())
    with caplog.at_level(logging.DEBUG, logger=SERDE_LOGGER):
        svc.run(
            job_description=persona_jd_text(),
            profile=persona_profile(),
            thread_id="t1",
            options=RunOptions(cover_letter=True),
        )
        svc.resume("t1", persona_answers().free_text)
        final = svc.resume_cover_letter("t1", "formal", "short")
        values = svc.get_state("t1")["values"]
    assert final["cover_letter"] == letter
    assert isinstance(values["eligibility"], Eligibility)
    assert "SECTION_RESTORED" in {w.code for w in values["warnings"]}
    assert [r.getMessage() for r in caplog.records if r.name.startswith(SERDE_LOGGER)] == []
