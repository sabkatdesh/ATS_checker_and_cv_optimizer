import logging
import os
import tempfile

from app.container import Container
from app.domain.credits.legacy import CV_GENERATION_COST
from app.ports.pipeline import JsonDict

logger = logging.getLogger(__name__)


def finalize_session(
    c: Container,
    thread_id: str,
    result: JsonDict,
    user_id: str,
    profile: JsonDict | None = None,
) -> None:
    """
    Called after pipeline finishes.
    1. Generates CV PDF (WeasyPrint via PDFGenerator)
    2. Optionally generates cover letter PDF (WeasyPrint via CoverLetterService)
    3. Uploads both PDFs to Supabase storage
    4. Deducts coins
    5. Updates session as complete
    """
    ats_score = None
    eligibility_score = None
    pdf_url = None

    # Get scores
    if result.get("final_match"):
        ats_score = result["final_match"].get("overall_score")

    if result.get("eligibility_verdict"):
        eligibility_score = result["eligibility_verdict"].score

    # Check if eligible — only generate PDF if eligible
    if not result.get("is_eligible"):
        c.store.update_session(
            thread_id,
            {
                "status": "ineligible",
                "eligibility_score": eligibility_score,
            },
        )
        return

    # Generate PDF using WeasyPrint + Jinja2 templates
    structured_cv = result.get("structured_cv")
    if not structured_cv:
        logger.info(
            "[PDF] No structured_cv in pipeline result for %s. Result keys: %s",
            thread_id,
            list(result.keys()),
        )
    if structured_cv:
        try:
            profile = profile or {}
            logger.info(
                "[PDF] Generating for %s, template=%s, domain=%s",
                thread_id,
                profile.get("preferred_template", "classic"),
                result.get("detected_domain", "general"),
            )
            generator = c.make_pdf_renderer()
            pdf_bytes = generator.render(
                cv_data=structured_cv,
                template_id=profile.get("preferred_template", "classic"),
                accent_color=profile.get("accent_color", "#4361ee"),
                bangla=bool(profile.get("bangla_mode", False)),
                domain=result.get("detected_domain", "general"),
            )

            local_path = os.path.join(tempfile.gettempdir(), f"{thread_id}.pdf")
            with open(local_path, "wb") as fh:
                fh.write(pdf_bytes)

            # Upload to Supabase storage
            pdf_url = c.store.upload_pdf_to_storage(thread_id, user_id, local_path)
            logger.info("[PDF] Uploaded successfully for %s", thread_id)

            # Clean up local file
            if os.path.exists(local_path):
                os.remove(local_path)

        except Exception:
            logger.exception("[PDF] Generation failed for %s", thread_id)

    # ── Cover letter PDF (optional) ─────────────────────────────────────────────
    cover_letter_pdf_url = None
    cover_letter_text = None
    cl_result = result.get("cover_letter_result")

    if cl_result:
        try:
            profile = profile or {}
            candidate_name = profile.get("full_name", "")
            tone = result.get("cover_letter_tone") or "formal"

            cl_service = c.make_cover_letter_renderer()
            cl_pdf_bytes = cl_service.render_to_pdf(
                cl_data=cl_result,
                tone=tone,
                candidate_name=candidate_name,
                bangla=bool(profile.get("bangla_mode", False)),
            )

            # Plain text version — stored so frontend can show editable draft
            cover_letter_text = cl_service.to_plain_text(cl_result, candidate_name)

            cl_local_path = os.path.join(tempfile.gettempdir(), f"{thread_id}_cl.pdf")
            with open(cl_local_path, "wb") as fh:
                fh.write(cl_pdf_bytes)

            cover_letter_pdf_url = c.store.upload_pdf_to_storage(
                f"{thread_id}_cover_letter", user_id, cl_local_path
            )

            if os.path.exists(cl_local_path):
                os.remove(cl_local_path)

        except Exception:
            logger.exception("Cover letter PDF generation failed for %s", thread_id)

    # Deduct coins
    c.store.deduct_coins(user_id, CV_GENERATION_COST, f"CV generation - thread {thread_id}")

    # Mark session as complete
    c.store.update_session(
        thread_id,
        {
            "status": "complete",
            "ats_score": ats_score,
            "eligibility_score": eligibility_score,
            "pdf_url": pdf_url,
            "cover_letter_text": cover_letter_text,
            "cover_letter_pdf_url": cover_letter_pdf_url,
        },
    )
