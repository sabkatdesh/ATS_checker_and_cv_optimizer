"""ProfileBuilder.detect_domain(profile): heuristic Domain for a profile dict (cv_profiles row)."""

from __future__ import annotations

from typing import Any

from app.domain.cv.domain_config import Domain
from app.domain.cv.profile_domain import detect_domain as _detect_domain_from_text


class ProfileBuilder:
    # ── Public API ──────────────────────────────────────────────────────────────

    @classmethod
    def detect_domain(cls, profile: dict[str, Any]) -> Domain:
        """
        Heuristic domain classification from profile fields.
        Used when the user has not explicitly selected a domain.
        """
        p = cls._normalise_keys(profile)

        text_corpus = cls._build_search_corpus(p).lower()
        licenses = [str(lic).lower() for lic in (p.get("licenses") or [])]
        license_text = " ".join(licenses)
        return _detect_domain_from_text(text_corpus, license_text)

    # ── Internal helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _normalise_keys(profile: dict[str, Any]) -> dict[str, Any]:
        """Map legacy DB keys to canonical block names."""
        p = dict(profile)
        # 'experience' in old DB → 'work_experience' in block order
        if "experience" in p and "work_experience" not in p:
            p["work_experience"] = p["experience"]
        # 'summary' in old DB → 'professional_summary' in block order
        if "summary" in p and "professional_summary" not in p:
            p["professional_summary"] = p["summary"]
        return p

    @staticmethod
    def _build_search_corpus(p: dict[str, Any]) -> str:
        """Flatten relevant profile fields into a single searchable string."""
        parts: list[str] = []
        for key in (
            "professional_summary",
            "skills",
            "work_experience",
            "education",
            "certifications",
            "publications",
            "trade_qualifications",
        ):
            val = p.get(key)
            if val:
                parts.append(str(val))
        return " ".join(parts)
