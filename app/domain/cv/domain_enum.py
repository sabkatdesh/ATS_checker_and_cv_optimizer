"""The Domain enum (one value per profession family)."""

from enum import Enum


class Domain(str, Enum):  # noqa: UP042
    TECH = "tech"
    MEDICAL = "medical"
    EDUCATION = "education"
    TRADES = "trades"
    FINANCE = "finance"
    LEGAL = "legal"
    CREATIVE = "creative"
    GENERAL = "general"
