class FakePdfRenderer:
    calls: list = []
    raise_on_render: Exception | None = None

    def render(
        self, cv_data, template_id="classic", accent_color="#4361ee", bangla=False, domain=None
    ) -> bytes:
        type(self).calls.append(
            (
                "render",
                (cv_data,),
                {
                    "template_id": template_id,
                    "accent_color": accent_color,
                    "bangla": bangla,
                    "domain": domain,
                },
            )
        )
        if type(self).raise_on_render is not None:
            raise type(self).raise_on_render
        return b"%PDF-fake-cv"


class FakeCoverLetterRenderer:
    calls: list = []
    raise_on_render: Exception | None = None

    def render_to_pdf(self, cl_data, tone="formal", candidate_name="", bangla=False) -> bytes:
        type(self).calls.append(
            (
                "render_to_pdf",
                (cl_data,),
                {"tone": tone, "candidate_name": candidate_name, "bangla": bangla},
            )
        )
        if type(self).raise_on_render is not None:
            raise type(self).raise_on_render
        return b"%PDF-fake-cl"

    def to_plain_text(self, cl_data, candidate_name="") -> str:
        type(self).calls.append(("to_plain_text", (cl_data,), {"candidate_name": candidate_name}))
        return "PLAIN COVER LETTER"
