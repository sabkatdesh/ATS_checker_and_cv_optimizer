"""
Safe LLM output parser — never crashes, always returns a usable value.

Three parse attempts:
  1. Direct json.loads
  2. Strip markdown ```json ... ``` block
  3. Extract first { ... } block

Usage (functional):
    from app.domain.parsing.safe_parser import safe_llm_parse
    result = safe_llm_parse(raw, MyModel, MyModel())

Usage (class):
    parser = SafeParser()
    result = parser.parse(raw, MyModel, MyModel())
"""

from __future__ import annotations

import json
import re
from typing import TypeVar

import structlog
from pydantic import BaseModel

log = structlog.get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


def safe_llm_parse(raw_text: str, model_class: type[T], fallback: T) -> T:  # noqa: UP047
    """
    Parse LLM raw string into a Pydantic model.
    Returns fallback if all attempts fail — never raises.
    """
    # Attempt 1: direct JSON
    try:
        return model_class.model_validate(json.loads(raw_text))
    except Exception:  # noqa: S110
        pass

    # Attempt 2: JSON inside markdown code block
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw_text)
    if m:
        try:
            return model_class.model_validate(json.loads(m.group(1)))
        except Exception:  # noqa: S110
            pass

    # Attempt 3: find first { ... } block (greedy, whole span)
    m = re.search(r"\{[\s\S]+\}", raw_text)
    if m:
        try:
            return model_class.model_validate(json.loads(m.group(0)))
        except Exception:  # noqa: S110
            pass

    # Attempt 4: find last complete JSON object (handles prose-then-JSON)
    for candidate in reversed(re.findall(r"\{[\s\S]+?\}", raw_text)):
        try:
            return model_class.model_validate(json.loads(candidate))
        except Exception:  # noqa: S112
            continue

    # Attempt 5: strip common LLM preambles then retry
    stripped = re.sub(r"^[^{\[]+", "", raw_text.strip())
    if stripped:
        try:
            return model_class.model_validate(json.loads(stripped))
        except Exception:  # noqa: S110
            pass

    log.warning("llm.parse_failed", model=model_class.__name__, raw_len=len(raw_text))
    return fallback


class SafeParser:
    """Class wrapper around safe_llm_parse for dependency-injection use cases."""

    def parse(self, raw_text: str, model_class: type[T], fallback: T) -> T:
        return safe_llm_parse(raw_text, model_class, fallback)
