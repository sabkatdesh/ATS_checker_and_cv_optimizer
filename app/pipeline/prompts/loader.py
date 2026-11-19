"""Versioned prompt files: front matter version, then `## system` and `## task` sections."""

import re
from dataclasses import dataclass
from pathlib import Path

from app.config.settings import ConfigError

PROMPTS_DIR = Path(__file__).parent

_VERSION_RE = re.compile(r"\A---\s*\nversion:\s*(\d+)\s*\n---\s*\n")
_SECTION_RE = re.compile(r"^## (system|task)[ \t]*\n", re.MULTILINE)


@dataclass(frozen=True)
class Prompt:
    step: str
    version: int
    system: str
    task: str

    def task_line(self, **params: int | float | str) -> str:
        return self.task.format(**params)


def _parse(step: str, text: str) -> Prompt:
    name = f"{step}.md"
    head = _VERSION_RE.match(text)
    if head is None:
        raise ConfigError(f"prompt {name}: missing version front matter")
    body = text[head.end() :]
    marks = list(_SECTION_RE.finditer(body))
    sections: dict[str, str] = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        sections[m.group(1)] = body[m.end() : end].strip()
    if not sections.get("system") or not sections.get("task"):
        raise ConfigError(f"prompt {name}: needs non-empty '## system' and '## task' sections")
    return Prompt(step, int(head.group(1)), sections["system"], sections["task"])


class PromptLibrary:
    def __init__(self, directory: Path = PROMPTS_DIR) -> None:
        self._dir = directory
        self._cache: dict[str, Prompt] = {}

    def get(self, step: str) -> Prompt:
        cached = self._cache.get(step)
        if cached is not None:
            return cached
        path = self._dir / f"{step}.md"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            raise ConfigError(f"prompt {step}.md: file not readable") from None
        prompt = _parse(step, text)
        self._cache[step] = prompt
        return prompt
