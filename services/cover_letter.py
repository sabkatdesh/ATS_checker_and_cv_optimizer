"""
Cover Letter Service — Phase 6.

Renders a CoverLetterStructured object to PDF bytes using WeasyPrint + Jinja2.
LLM generation happens inside the pipeline node (generate_cover_letter_node).
This service only handles PDF rendering and plain-text export.

Usage:
    service = CoverLetterService()
    pdf_bytes = service.render_to_pdf(cl_result, tone="formal", candidate_name="Jane Doe")
    plain_text = service.to_plain_text(cl_result, candidate_name="Jane Doe")
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

import jinja2

from core.schemas.cover_letter_schemas import CoverLetterStructured

_ROOT = Path(__file__).parent.parent
_CL_TEMPLATES_DIR = _ROOT / "templates" / "cover_letter"

VALID_TONES = {"formal", "conversational"}


class CoverLetterService:
    def __init__(self) -> None:
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(_CL_TEMPLATES_DIR)),
            autoescape=False,
            undefined=jinja2.Undefined,
        )
        self._wp_html = None
        self._wp_font_config = None
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
        return self._wp_error is None

    def render_to_pdf(
        self,
        cl_data: Union[CoverLetterStructured, dict],
        tone: str = "formal",
        candidate_name: str = "",
        bangla: bool = False,
    ) -> bytes:
        """
        Render a cover letter to PDF bytes.

        Args:
            cl_data:        CoverLetterStructured or plain dict from model_dump()
            tone:           Template variant — "formal" or "conversational"
            candidate_name: Displayed as the sender name in the sign-off block
            bangla:         If True, activates Hind Siliguri font

        Raises:
            RuntimeError: if WeasyPrint is not available
            FileNotFoundError: if the template file is missing
        """
        if self._wp_error:
            raise RuntimeError(self._wp_error)

        if hasattr(cl_data, "model_dump"):
            cl_dict = cl_data.model_dump()
        elif isinstance(cl_data, dict):
            cl_dict = cl_data
        else:
            cl_dict = {}

        tone = tone if tone in VALID_TONES else "formal"
        template_name = f"{tone}.html"

        fonts_dir = str(_ROOT / "templates" / "fonts")
        base_css_path = str(_ROOT / "templates" / "base.css")

        template = self._env.get_template(template_name)
        html_str = template.render(
            cl=cl_dict,
            candidate_name=candidate_name,
            bangla=bangla,
            fonts_dir=fonts_dir,
            base_css_path=base_css_path,
        )

        font_config = self._wp_font_config()
        pdf_bytes = self._wp_html(string=html_str).write_pdf(font_config=font_config)
        return pdf_bytes

    def to_plain_text(
        self,
        cl_data: Union[CoverLetterStructured, dict],
        candidate_name: str = "",
    ) -> str:
        """Export cover letter as plain text (for editable textarea in frontend)."""
        if hasattr(cl_data, "model_dump"):
            d = cl_data.model_dump()
        elif isinstance(cl_data, dict):
            d = cl_data
        else:
            return ""

        parts = [
            d.get("salutation", ""),
            "",
            d.get("opening_paragraph", ""),
        ]

        for para in d.get("body_paragraphs", []):
            parts.append("")
            parts.append(para)

        parts.append("")
        parts.append(d.get("closing_paragraph", ""))
        parts.append("")
        parts.append(d.get("sign_off", ""))

        if candidate_name:
            parts.append(candidate_name)

        return "\n".join(parts)
