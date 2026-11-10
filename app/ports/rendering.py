from typing import Any, Protocol


class CvPdfRenderer(Protocol):
    def render(
        self,
        cv_data: Any,
        template_id: str = "classic",
        accent_color: str = "#4361ee",
        bangla: bool = False,
        domain: str | None = None,
    ) -> bytes: ...


class CoverLetterRenderer(Protocol):
    def render_to_pdf(
        self, cl_data: Any, tone: str = "formal", candidate_name: str = "", bangla: bool = False
    ) -> bytes: ...

    def to_plain_text(self, cl_data: Any, candidate_name: str = "") -> str: ...
