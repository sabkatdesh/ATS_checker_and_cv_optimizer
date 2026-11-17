"""Types the graph checkpointer may deserialize. Add each new state type to STATE_TYPES."""

import types
import typing
from enum import Enum
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic import BaseModel

from app.domain.ats.schemas import AtsMatch
from app.domain.cv.cover_letter import CoverLetterStructured
from app.domain.cv.rewrite import RewrittenCV
from app.domain.cv.universal_cv import UniversalCVStructured
from app.domain.jd.schemas import JobDescriptionStructured
from app.domain.match.schemas import Eligibility
from app.domain.questions.schemas import GapAnswers, GapQuestion, GapQuestions
from app.domain.trust.report import TrustReport
from app.pipeline.state import RunOptions
from app.pipeline.warnings import PipelineWarning

# Top-level state values; nested models and enums are found from their fields.
STATE_TYPES: tuple[type, ...] = (
    RunOptions,
    JobDescriptionStructured,
    UniversalCVStructured,
    Eligibility,
    GapQuestion,
    GapQuestions,
    GapAnswers,
    AtsMatch,
    RewrittenCV,
    CoverLetterStructured,
    TrustReport,
    PipelineWarning,
)


def _nested(annotation: Any) -> list[type]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel | Enum):
        return [annotation]
    origin = typing.get_origin(annotation)
    if origin is None and not isinstance(annotation, types.UnionType):
        return []
    return [t for arg in typing.get_args(annotation) for t in _nested(arg)]


def _closure(roots: tuple[type, ...]) -> list[type]:
    seen: list[type] = []
    stack = list(roots)
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.append(cls)
        if issubclass(cls, BaseModel):
            for field in cls.model_fields.values():
                stack.extend(_nested(field.annotation))
    return seen


def allowed_modules() -> list[tuple[str, str]]:
    return sorted({(cls.__module__, cls.__qualname__) for cls in _closure(STATE_TYPES)})


def checkpoint_serde() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=allowed_modules())


def new_checkpointer() -> MemorySaver:
    """In-memory checkpointer with the state allowlist (the app and the graph tests use it)."""
    return MemorySaver(serde=checkpoint_serde())
