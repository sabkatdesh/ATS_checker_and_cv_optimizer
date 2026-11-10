"""
ProfileBuilder — converts a profile dict (from cv_profiles table) to resume text.

Two entry points:
  ProfileBuilder.from_profile_dict(profile, domain)  → plain text string
  ProfileBuilder.detect_domain(profile)              → Domain enum value

Block rendering follows DOMAIN_BLOCK_ORDER so section order matches the PDF renderer.
Empty blocks are silently skipped — no "LICENSES\n(none)" headings.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.domain.cv import profile_sections_core as core_blocks
from app.domain.cv import profile_sections_extra as extra_blocks
from app.domain.cv.domain_config import Domain, get_block_order
from app.domain.cv.profile_domain import detect_domain as _detect_domain_from_text

_RENDERERS: dict[str, Callable[[dict[str, Any], list[str]], None]] = {
    "meta": core_blocks.render_meta,
    "professional_summary": core_blocks.render_professional_summary,
    "skills": core_blocks.render_skills,
    "work_experience": core_blocks.render_work_experience,
    "education": core_blocks.render_education,
    "certifications": core_blocks.render_certifications,
    "projects": core_blocks.render_projects,
    "publications": extra_blocks.render_publications,
    "licenses": extra_blocks.render_licenses,
    "clinical_practice": extra_blocks.render_clinical_practice,
    "trade_qualifications": extra_blocks.render_trade_qualifications,
    "languages": extra_blocks.render_languages,
    "volunteering": extra_blocks.render_volunteering,
    "awards": extra_blocks.render_awards,
}


class ProfileBuilder:
    # ── Public API ──────────────────────────────────────────────────────────────

    @classmethod
    def from_profile_dict(cls, profile: dict[str, Any], domain: Domain | str | None = None) -> str:
        """
        Convert a cv_profiles row (dict) to plain-text resume string.

        Args:
            profile: dict from Supabase cv_profiles table
            domain:  Domain enum or string; auto-detected from profile when None
        """
        if not profile:
            return ""

        resolved = cls._resolve_domain(profile, domain)
        block_order = get_block_order(resolved)

        # Profile dict uses legacy key names in some places; normalise first.
        # (The DB may use 'experience' while the block order uses 'work_experience')
        p = cls._normalise_keys(profile)

        lines: list[str] = []
        for block in block_order:
            renderer = _RENDERERS.get(block)
            if renderer:
                renderer(p, lines)

        # References line at very end when flag is set
        if p.get("references_available"):
            lines.append("")
            lines.append("References available upon request.")

        return "\n".join(lines)

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
    def _resolve_domain(profile: dict[str, Any], domain: Domain | str | None) -> Domain:
        if domain is not None:
            return Domain(domain) if isinstance(domain, str) else domain
        stored = profile.get("domain")
        if stored and stored != "unknown":
            try:
                return Domain(stored)
            except ValueError:
                pass
        return ProfileBuilder.detect_domain(profile)

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


# ── Compatibility shim for old callers ──────────────────────────────────────────


def profile_to_resume_text(profile: dict[str, Any]) -> str:
    """Legacy wrapper. New code should call ProfileBuilder.from_profile_dict()."""
    return ProfileBuilder.from_profile_dict(profile)
