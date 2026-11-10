"""
PDF generation service — Phase 5.

Uses WeasyPrint (HTML→PDF) + Jinja2 (templating) to render structured CV data
into a styled PDF document.

Usage:
    generator = PDFGenerator()
    pdf_bytes = generator.render(cv_data, template_id="classic", accent_color="#4361ee")

WeasyPrint on Windows requires the GTK runtime:
    https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases
On Linux:
    sudo apt-get install libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import jinja2

from app.domain.cv.domain_config import get_block_order

# ── Directory paths ───────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATES_DIR = _ROOT / "templates" / "cv"
_FONTS_DIR = _ROOT / "templates" / "fonts"

VALID_TEMPLATES = {"classic", "modern", "compact", "academic", "trades", "creative"}


def _month_year(value) -> str:
    """Format an ISO date string or None as 'Mon YYYY' / 'Present'."""
    if not value:
        return "Present"
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%b %Y")
    except Exception:
        return str(value)[:7]


class PDFGenerator:
    """
    Renders a CV (UniversalCVStructured / RewrittenCV / dict) to PDF bytes.

    Template IDs match files in templates/cv/:
        classic  — 1-column, ATS-safe, all professions
        modern   — 2-column sidebar, tech / finance / corporate
        compact  — 1-page dense, freshers
        academic — long-form, research / teaching / medical
        trades   — bold headers, licenses front-loaded
        creative — bold header + 2-column, designers / marketers

    Args:
        cv_data:      Pydantic model or plain dict from model_dump()
        template_id:  One of VALID_TEMPLATES; falls back to 'classic' if unknown
        accent_color: CSS colour string e.g. '#4361ee'
        bangla:       True → activates Hind Siliguri font + lang="bn"
        domain:       Overrides cv_data.domain for block ordering
    """

    def __init__(self) -> None:
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
            autoescape=False,  # noqa: S701  PDF renderer, not a browser
            undefined=jinja2.Undefined,
        )
        self._env.filters["month_year"] = _month_year

        # Lazy-load WeasyPrint so import failures produce a clear runtime error
        self._wp_html: Any = None
        self._wp_font_config: Any = None
        self._wp_error: str | None = None
        self._load_weasyprint()

    def _load_weasyprint(self) -> None:
        try:
            from weasyprint import HTML
            from weasyprint.text.fonts import FontConfiguration

            self._wp_html = HTML
            self._wp_font_config = FontConfiguration
        except (ImportError, OSError) as exc:
            self._wp_error = (
                f"WeasyPrint unavailable: {exc}\n"
                "  Windows: install GTK runtime from "
                "https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases\n"
                "  Linux:   sudo apt-get install libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0"
            )

    @property
    def available(self) -> bool:
        """True if WeasyPrint loaded successfully."""
        return self._wp_error is None

    def render(
        self,
        cv_data: dict | object,
        template_id: str = "classic",
        accent_color: str = "#4361ee",
        bangla: bool = False,
        domain: str | None = None,
    ) -> bytes:
        """
        Render cv_data to PDF bytes using the specified template.

        Raises:
            RuntimeError: if WeasyPrint is not available (missing GTK on Windows)
            FileNotFoundError: if template_id resolves to a missing .html file
        """
        if self._wp_error:
            raise RuntimeError(self._wp_error)

        # ── Convert cv_data to plain dict ──────────────────────────────────────
        if hasattr(cv_data, "model_dump"):
            cv_dict = cv_data.model_dump()
        elif isinstance(cv_data, dict):
            cv_dict = cv_data
        else:
            cv_dict = {}

        # ── Resolve domain ─────────────────────────────────────────────────────
        if domain is None:
            domain = cv_dict.get("domain", "general")
            if hasattr(domain, "value"):
                domain = domain.value

        # ── Validate template ──────────────────────────────────────────────────
        if template_id not in VALID_TEMPLATES:
            template_id = "classic"

        block_order = get_block_order(domain)

        # ── Ensure nested dicts have safe defaults ─────────────────────────────
        cv_dict = _ensure_defaults(cv_dict)

        # ── Render Jinja2 template ─────────────────────────────────────────────
        template = self._env.get_template(f"{template_id}.html")
        html_str = template.render(
            cv=cv_dict,
            block_order=block_order,
            accent=accent_color,
            lang="bn" if bangla else "en",
        )

        # ── WeasyPrint → PDF bytes ─────────────────────────────────────────────
        font_config = self._wp_font_config()
        return self._wp_html(
            string=html_str,
            base_url=str(_TEMPLATES_DIR) + "/",
        ).write_pdf(font_config=font_config)

    def render_to_file(
        self,
        path: str,
        cv_data: dict | object,
        **kwargs,
    ) -> None:
        """Convenience wrapper — renders and writes to a file path."""
        pdf_bytes = self.render(cv_data, **kwargs)
        with open(path, "wb") as fh:
            fh.write(pdf_bytes)


def _ensure_defaults(cv: dict) -> dict:
    """Fill in missing nested keys so templates can access them without crashing."""
    cv.setdefault("meta", {})
    cv["meta"].setdefault("full_name", None)
    cv["meta"].setdefault("location", None)
    cv["meta"].setdefault("email", None)
    cv["meta"].setdefault("phone", None)
    cv["meta"].setdefault("linkedin", None)
    cv["meta"].setdefault("optional_links", {})

    cv.setdefault("professional_summary", None)

    cv.setdefault("skills", {})
    cv["skills"].setdefault("hard_skills", [])
    cv["skills"].setdefault("soft_skills", [])
    cv["skills"].setdefault("tools", [])
    cv["skills"].setdefault("frameworks", [])
    cv["skills"].setdefault("cloud_platforms", [])

    cv.setdefault("experience_summary", {})
    cv["experience_summary"].setdefault("role_type", None)
    cv["experience_summary"].setdefault("seniority", "unknown")

    for list_key in (
        "work_experience",
        "education",
        "certifications",
        "projects",
        "publications",
        "licenses",
        "clinical_practice",
        "trade_qualifications",
        "languages",
        "volunteering",
        "awards",
    ):
        cv.setdefault(list_key, [])
        if cv[list_key] is None:
            cv[list_key] = []

    cv.setdefault("references_available", False)

    return cv
