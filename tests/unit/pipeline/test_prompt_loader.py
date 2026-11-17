from pathlib import Path

import pytest

from app.config.settings import ConfigError
from app.pipeline.blocks import INJECTION_RULE
from app.pipeline.prompts.loader import PROMPTS_DIR, PromptLibrary

STEPS = [
    "jd_extract",
    "cv_extract",
    "eligibility",
    "gap_questions",
    "rewrite",
    "verify_claims",
    "revise_flagged",
    "cover_letter",
]


def write(tmp_path: Path, name: str, text: str) -> None:
    (tmp_path / f"{name}.md").write_text(text, encoding="utf-8")


def test_loads_version_system_task(tmp_path: Path) -> None:
    write(tmp_path, "x", "---\nversion: 3\n---\n## system\nBe good.\n## task\nDo it.\n")
    p = PromptLibrary(tmp_path).get("x")
    assert (p.step, p.version, p.system, p.task) == ("x", 3, "Be good.", "Do it.")


def test_missing_version_raises_config_error(tmp_path: Path) -> None:
    write(tmp_path, "x", "## system\nA\n## task\nB\n")
    with pytest.raises(ConfigError, match="x.md"):
        PromptLibrary(tmp_path).get("x")


def test_missing_section_raises_config_error(tmp_path: Path) -> None:
    write(tmp_path, "x", "---\nversion: 1\n---\n## system\nA\n")
    with pytest.raises(ConfigError, match="x.md"):
        PromptLibrary(tmp_path).get("x")


def test_missing_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="nope.md"):
        PromptLibrary(tmp_path).get("nope")


def test_task_line_fills_code_params(tmp_path: Path) -> None:
    write(tmp_path, "x", "---\nversion: 1\n---\n## system\nA\n## task\nUse {max_roles} roles\n")
    assert PromptLibrary(tmp_path).get("x").task_line(max_roles=4) == "Use 4 roles"


def test_task_line_missing_param_raises_keyerror(tmp_path: Path) -> None:
    write(tmp_path, "x", "---\nversion: 1\n---\n## system\nA\n## task\nUse {max_roles} roles\n")
    with pytest.raises(KeyError):
        PromptLibrary(tmp_path).get("x").task_line()


def test_prompts_are_cached(tmp_path: Path) -> None:
    write(tmp_path, "x", "---\nversion: 1\n---\n## system\nA\n## task\nB\n")
    lib = PromptLibrary(tmp_path)
    assert lib.get("x") is lib.get("x")


@pytest.mark.parametrize("step", STEPS)
def test_every_llm_step_has_a_prompt(step: str) -> None:
    prompt = PromptLibrary().get(step)
    assert prompt.version >= 1
    assert prompt.system
    assert prompt.task


@pytest.mark.parametrize("step", STEPS)
def test_system_text_has_no_placeholders(step: str) -> None:
    assert "{" not in PromptLibrary().get(step).system


@pytest.mark.parametrize("step", STEPS)
def test_every_prompt_has_injection_rule(step: str) -> None:
    assert INJECTION_RULE in PromptLibrary().get(step).system


def test_every_prompt_file_is_a_tested_step() -> None:
    files = sorted(p.stem for p in PROMPTS_DIR.glob("*.md"))
    assert files == sorted(STEPS)
