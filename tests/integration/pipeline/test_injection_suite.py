"""Hostile job descriptions through the real graph: flagged, isolated in data blocks, no effect."""

import json
import re
from pathlib import Path
from typing import get_args

import pytest

from app.domain.cv.rewrite import RewrittenCV
from app.domain.match.schemas import Eligibility
from app.domain.questions.schemas import GapQuestion, GapQuestions
from app.domain.text.invisible import strip_invisible
from app.domain.trust.judge import JudgeFindings
from app.pipeline.blocks import DataTag
from app.pipeline.checkpoint_types import new_checkpointer
from app.pipeline.graph import build_graph
from app.pipeline.service import PipelineService
from app.pipeline.state import RunOptions
from tests.pipeline.helpers import deps_for, persona_answers, persona_cv, persona_jd_text, tech_jd
from tests.pipeline.scripted_gateway import ScriptedGateway

INJECTION = Path(__file__).resolve().parents[2] / "fixtures" / "injection"
CASES = json.loads((INJECTION / "cases.json").read_text(encoding="utf-8"))
_TAGS = "|".join(get_args(DataTag))
_BLOCK = re.compile(rf"<({_TAGS})>\n.*?\n</\1>", re.DOTALL)
EVIL_URL = "https://evil.example/apply"


def _draft(bullet_suffix: str = "") -> RewrittenCV:
    cv = RewrittenCV.model_validate(persona_cv().model_dump())
    role = cv.work_experience[0]
    bullets = [f"{b}{bullet_suffix}" for b in role.responsibilities]
    return cv.model_copy(
        update={"work_experience": [role.model_copy(update={"responsibilities": bullets})]}
    )


def _run(jd_text: str, draft: RewrittenCV) -> tuple[ScriptedGateway, dict]:
    gw, deps = deps_for(
        {
            "jd_extract": [tech_jd()],
            "cv_extract": [persona_cv()],
            "eligibility": [Eligibility(score=60, gaps=["Kubernetes"])],
            "gap_questions": [GapQuestions(questions=[GapQuestion(id="q1", text="K8s?")])],
            "rewrite": [draft for _ in range(3)],
            "verify_claims": [JudgeFindings()],
        }
    )
    svc = PipelineService(build_graph(deps, new_checkpointer()), deps.runs)
    svc.run(
        job_description=jd_text, user_resume_text="cv text", thread_id="t", options=RunOptions()
    )
    return gw, svc.resume("t", persona_answers().free_text)


def _hostile_lines(case: dict) -> list[str]:
    clean = set(persona_jd_text(case["clean_twin"]).splitlines())
    text = (INJECTION / case["file"]).read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line not in clean]


@pytest.fixture(scope="module")
def clean_run() -> tuple[ScriptedGateway, dict]:
    return _run(persona_jd_text("tech_backend"), _draft())


@pytest.mark.parametrize("case", CASES, ids=[c["file"] for c in CASES])
def test_hostile_jd_is_flagged_isolated_and_harmless(case: dict, clean_run) -> None:
    clean_gw, clean = clean_run
    gw, final = _run((INJECTION / case["file"]).read_text(encoding="utf-8"), _draft())
    # (a) the run carries the marker warning; the clean run does not
    assert "JD_INJECTION_MARKERS" in {w.code for w in final["warnings"]}
    assert "JD_INJECTION_MARKERS" not in {w.code for w in clean["warnings"]}
    # (b) the system messages are byte-identical to the clean run
    assert [(r.step, r.system) for r in gw.requests] == [
        (r.step, r.system) for r in clean_gw.requests
    ]
    # (c) outside the data blocks nothing differs and no hostile sentence survives
    hostile = _hostile_lines(case)
    assert hostile
    for req, clean_req in zip(gw.requests, clean_gw.requests, strict=True):
        rest = _BLOCK.sub("", req.messages[0].content)
        assert rest == _BLOCK.sub("", clean_req.messages[0].content)
        for line in hostile:
            assert strip_invisible(line).strip() not in rest and line not in rest
    # (d) deterministic outcomes are unchanged
    assert final["ats_before"].score == clean["ats_before"].score
    assert final["eligible"] == clean["eligible"]


def test_compliant_rewrite_cannot_insert_the_url() -> None:
    jd = (INJECTION / "06_url_insertion.txt").read_text(encoding="utf-8")
    gw, final = _run(jd, _draft(f" {EVIL_URL}"))
    assert EVIL_URL in gw.requests[0].messages[0].content  # the JD itself still reaches the model
    assert "evil.example" not in final["tailored_cv"].model_dump_json()
    assert "FOREIGN_CONTACT_REMOVED" in {w.code for w in final["warnings"]}
