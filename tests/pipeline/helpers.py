"""Shared builders for pipeline tests: deps, run context, persona fixtures."""

import asyncio
import json
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

from app.config.pipeline_settings import PipelineSettings
from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.jd.schemas import JobDescriptionStructured
from app.domain.questions.schemas import GapAnswers
from app.pipeline.context import RunContext
from app.pipeline.deps import PipelineDeps
from app.pipeline.prompts.loader import PromptLibrary
from app.ports.llm import CancelToken
from tests.pipeline.scripted_gateway import Outcome, ScriptedGateway

PERSONAS = Path(__file__).resolve().parents[1] / "fixtures" / "personas"
_JD_FILE = Path(__file__).resolve().parents[2] / "app/adapters/llm/fake_responses/jd_extract.json"


def deps_for(
    script: dict[str, list[Outcome]], **settings: Any
) -> tuple[ScriptedGateway, PipelineDeps]:
    gw = ScriptedGateway(script)
    return gw, PipelineDeps(
        gateway=gw, prompts=PromptLibrary(), settings=PipelineSettings(**settings)
    )


def ctx() -> RunContext:
    return RunContext(session_id="s-1", cancel=CancelToken())


def run[R](coro: Coroutine[Any, Any, R]) -> R:
    return asyncio.run(coro)


def persona_cv(name: str = "tech_backend") -> UniversalCVStructured:
    return UniversalCVStructured.model_validate_json(
        (PERSONAS / name / "cv.json").read_text(encoding="utf-8")
    )


def persona_profile(name: str = "tech_backend") -> dict[str, Any]:
    """The persona's saved profile (legacy `cv_profiles` row shape); it converts to cv.json."""
    profile: dict[str, Any] = json.loads(
        (PERSONAS / name / "profile.json").read_text(encoding="utf-8")
    )
    return profile


def legacy_profile(cv: UniversalCVStructured) -> dict[str, Any]:
    """A saved-profile row that converts back to `cv` (for tests that build their own CV)."""
    data = cv.model_dump(mode="json", exclude={"quality_flags"})
    meta = data.pop("meta")
    links = meta.pop("optional_links") or {}
    profile = {k: v for k, v in meta.items() if v is not None}
    for label, key in (("GitHub", "github"), ("Portfolio", "portfolio")):
        if label in links:
            profile[key] = links[label]
    profile["summary"] = data.pop("professional_summary")
    profile["experience"] = data.pop("work_experience")
    return {**profile, **data}


def persona_jd_text(name: str = "tech_backend") -> str:
    return (PERSONAS / name / "jd.txt").read_text(encoding="utf-8")


def persona_answers(name: str = "tech_backend") -> GapAnswers:
    return GapAnswers.model_validate(
        json.loads((PERSONAS / name / "answers.json").read_text(encoding="utf-8"))
    )


def tech_jd() -> JobDescriptionStructured:
    return JobDescriptionStructured.model_validate_json(_JD_FILE.read_text(encoding="utf-8"))
