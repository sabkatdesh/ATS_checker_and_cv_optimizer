"""Shared domain primitives used by CV and JD schemas, plus UUIDv7 ids."""

from __future__ import annotations

import secrets
import time
import uuid
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


# ─── Ids ────────────────────────────────────────────────────────────────────────


def uuid7() -> str:
    """RFC 9562 UUIDv7: 48-bit unix-ms timestamp, then random bits (sorts by creation time)."""
    ms = time.time_ns() // 1_000_000
    value = (ms & ((1 << 48) - 1)) << 80 | secrets.randbits(80)
    value = (value & ~(0xF << 76)) | (0x7 << 76)  # version 7
    value = (value & ~(0x3 << 62)) | (0x2 << 62)  # RFC 4122 variant
    return str(uuid.UUID(int=value))
