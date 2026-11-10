"""Shared domain primitives used by CV and JD schemas."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import model_validator

# ─── Null-safe mixin ────────────────────────────────────────────────────────────


class NullSafeListMixin:
    """Coerces None → [] for all List fields. Guards against LLM returning null."""

    @model_validator(mode="before")
    @classmethod
    def coerce_none_lists(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        fields = cls.model_fields if hasattr(cls, "model_fields") else {}
        for key, value in data.items():
            if value is None and key in fields:
                annotation = str(fields[key].annotation)
                if "List" in annotation or "list" in annotation:
                    data[key] = []
        return data


# ─── Seniority ──────────────────────────────────────────────────────────────────


class SeniorityLevel(str, Enum):  # noqa: UP042
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    MANAGER = "manager"
    DIRECTOR = "director"
    UNKNOWN = "unknown"
