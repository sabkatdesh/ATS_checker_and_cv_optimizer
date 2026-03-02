"""
CV to PDF Converter — Layer 6 Hardened
Production-safe against None dates, None meta, bad unicode, empty sections,
and any malformed LLM-generated CV data.
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib import colors
from pydantic_class import UserCVStructured
import re


# ============================================================
# SAFETY UTILITIES
# ============================================================

def safe_text(value, default=""):
    """Return safe string — never None, never crash"""
    if value is None:
        return default
    return str(value).strip()


def safe_list(value):
    """Ensure value is always an iterable list"""
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if item is not None]  # ← CHANGED: also filters None items inside list
    return [value]


def clean_unicode(text):
    """
    Replace or remove every character reportlab's Helvetica cannot render.
    This is what was causing the black ■ boxes in your PDF.
    """
    if not text:
        return ""
    text = str(text)

    # Whitespace variants → regular space
    text = text.replace("\u202f", " ")    # narrow no-break space
    text = text.replace("\xa0",   " ")    # non-breaking space
    text = text.replace("\u200b", "")     # zero-width space
    text = text.replace("\ufeff", "")     # BOM

    # Dashes → plain hyphen
    text = text.replace("\u2013", "-")    # en dash  –
    text = text.replace("\u2014", "-")    # em dash  —
    text = text.replace("\u2212", "-")    # minus sign

    # Smart quotes → straight quotes
    text = text.replace("\u2018", "'")    # left single  '
    text = text.replace("\u2019", "'")    # right single '
    text = text.replace("\u201c", '"')    # left double  "
    text = text.replace("\u201d", '"')    # right double "

    # Bullets / shapes → hyphen
    text = text.replace("\u2022", "-")    # bullet •
    text = text.replace("\u25aa", "-")    # small square ▪
    text = text.replace("\u25cf", "-")    # black circle ●
    text = text.replace("\u25a0", "-")    # BLACK SQUARE ■  ← the main culprit
    text = text.replace("\ufffd", "")     # replacement char

    # Ellipsis
    text = text.replace("\u2026", "...")

    # Nuclear option: strip anything Helvetica cannot render
    cleaned = ""
    for ch in text:
        if ord(ch) < 128 or 0x00C0 <= ord(ch) <= 0x017F:
            cleaned += ch
        else:
            cleaned += " "

    # Collapse multiple spaces
    cleaned = re.sub(r" {2,}", " ", cleaned)

    return cleaned.strip()


def safe_paragraph(text, style):
    """
    Safely create a Paragraph — never crashes.
    Returns None if text is empty so caller can skip appending it.
    """
    cleaned = clean_unicode(safe_text(text))
    if not cleaned:
        return None
    try:
        return Paragraph(cleaned, style)
    except Exception as e:
        print(f"⚠️ Paragraph creation failed: {e}")
        return None


def safe_date_range(exp) -> str:
    """
    Safely format date range from a work experience entry.
    Handles None start_date, None end_date, and bad date objects.
    """
    try:
        start = exp.start_date.strftime("%b %Y") if exp.start_date else None
        end   = exp.end_date.strftime("%b %Y")   if exp.end_date   else "Present"

        if start:
            return f"{start} - {end}"
        elif exp.end_date:
            return f"Until {end}"
        else:
            return ""   # both None — show nothing, don't crash
    except Exception:
        return ""        # date object was malformed — show nothing, don't crash


# ============================================================
# STYLES
# ============================================================

def create_cv_styles():
    styles = getSampleStyleSheet()

    style_defs = [
        ("CVName", "Heading1", {
            "fontSize": 24, "textColor": colors.HexColor("#1a1a1a"),
            "alignment": TA_CENTER, "spaceAfter": 6, "fontName": "Helvetica-Bold"
        }),
        ("ContactInfo", "Normal", {
            "fontSize": 10, "alignment": TA_CENTER,
            "textColor": colors.HexColor("#555555"), "spaceAfter": 12
        }),
        ("SectionHeading", "Heading2", {
            "fontSize": 14, "fontName": "Helvetica-Bold",
            "textColor": colors.HexColor("#2c3e50"), "spaceBefore": 12, "spaceAfter": 8
        }),
        ("JobTitle", "Normal", {
            "fontSize": 11, "fontName": "Helvetica-Bold",
            "textColor": colors.HexColor("#2c3e50"), "spaceAfter": 2
        }),
        ("CompanyName", "Normal", {
            "fontSize": 10, "fontName": "Helvetica-Oblique",
            "textColor": colors.HexColor("#555555"), "spaceAfter": 2
        }),
        ("DateRange", "Normal", {
            "fontSize": 9, "textColor": colors.HexColor("#777777"), "spaceAfter": 4
        }),
        ("CVBodyText", "Normal", {
            "fontSize": 10, "alignment": TA_JUSTIFY, "leading": 14,
            "textColor": colors.HexColor("#333333"), "spaceAfter": 6
        }),
        ("BulletPoint", "Normal", {
            "fontSize": 10, "leftIndent": 18, "spaceAfter": 4,
            "leading": 13, "textColor": colors.HexColor("#333333")
        }),
        ("SkillItem", "Normal", {
            "fontSize": 10, "spaceAfter": 4, "textColor": colors.HexColor("#444444")
        }),
    ]

    for name, parent, kwargs in style_defs:
        if name not in styles:
            styles.add(ParagraphStyle(name=name, parent=styles[parent], **kwargs))

    return styles


# ============================================================
# SECTION BUILDERS — each returns a list of flowables
# These are broken into separate functions so a crash in one
# section never kills the entire PDF build.
# ← CHANGED: was all one giant function — now each section is isolated
# ============================================================

def build_header(cv_data, styles) -> list:
    story = []
    try:
        name = safe_paragraph(
            getattr(cv_data.meta, "full_name", None), styles["CVName"]
        )
        if name:
            story.append(name)

        contact_parts = []
        for field, label in [
            ("email",    None),
            ("phone",    None),
            ("location", None),
            ("linkedin", "LinkedIn"),
            ("github",   "GitHub"),
            ("portfolio","Portfolio"),
        ]:
            val = getattr(cv_data.meta, field, None)
            if val:
                contact_parts.append(f"{label}: {val}" if label else val)

        if contact_parts:
            contact_para = safe_paragraph(" | ".join(contact_parts), styles["ContactInfo"])
            if contact_para:
                story.append(contact_para)

        story.append(Spacer(1, 0.2 * inch))
    except Exception as e:
        print(f"⚠️ Header section failed: {e}")
    return story


def build_summary(cv_data, styles) -> list:
    story = []
    try:
        summary = getattr(cv_data, "professional_summary", None)
        if summary:
            story.append(Paragraph("Professional Summary", styles["SectionHeading"]))
            para = safe_paragraph(summary, styles["CVBodyText"])
            if para:
                story.append(para)
    except Exception as e:
        print(f"⚠️ Summary section failed: {e}")
    return story


def build_skills(cv_data, styles) -> list:
    story = []
    try:
        skills = getattr(cv_data, "skills", None)
        if not skills:
            return story

        skill_groups = [
            ("hard_skills",    "Hard Skills"),
            ("tools",          "Tools"),
            ("frameworks",     "Frameworks"),
            ("cloud_platforms","Cloud Platforms"),
            ("soft_skills",    "Soft Skills"),
        ]

        has_any = any(
            safe_list(getattr(skills, field, None))
            for field, _ in skill_groups
        )
        if not has_any:
            return story

        story.append(Paragraph("Skills", styles["SectionHeading"]))

        for field, label in skill_groups:
            items = safe_list(getattr(skills, field, None))
            # ← CHANGED: each skill item also cleaned through clean_unicode
            items = [clean_unicode(safe_text(i)) for i in items if i]
            if items:
                text = f"<b>{label}:</b> " + ", ".join(items)
                para = safe_paragraph(text, styles["SkillItem"])
                if para:
                    story.append(para)

    except Exception as e:
        print(f"⚠️ Skills section failed: {e}")
    return story


def build_experience(cv_data, styles) -> list:
    story = []
    try:
        work_exp = safe_list(getattr(cv_data, "work_experience", None))
        if not work_exp:
            return story

        story.append(Paragraph("Professional Experience", styles["SectionHeading"]))

        for exp in work_exp:
            section = []
            try:
                job = safe_paragraph(
                    getattr(exp, "job_title", "Role not specified"), styles["JobTitle"]
                )
                if job:
                    section.append(job)

                company = safe_paragraph(
                    safe_text(getattr(exp, "company_name", None), "Independent / Freelance"),
                    styles["CompanyName"]
                )
                if company:
                    section.append(company)

                # ← CHANGED: date range now uses safe_date_range() — never crashes on None dates
                date_str = safe_date_range(exp)
                if date_str:
                    date_para = safe_paragraph(date_str, styles["DateRange"])
                    if date_para:
                        section.append(date_para)

                for r in safe_list(getattr(exp, "responsibilities", [])):
                    para = safe_paragraph(f"- {safe_text(r)}", styles["BulletPoint"])
                    if para:
                        section.append(para)

                for a in safe_list(getattr(exp, "achievements", [])):
                    para = safe_paragraph(f"+ {safe_text(a)}", styles["BulletPoint"])
                    if para:
                        section.append(para)

                if section:
                    story.append(KeepTogether(section))
                    story.append(Spacer(1, 0.12 * inch))

            except Exception as e:
                # ← CHANGED: one bad experience entry skips itself, doesn't kill the rest
                print(f"⚠️ Skipping malformed experience entry: {e}")
                continue

    except Exception as e:
        print(f"⚠️ Experience section failed: {e}")
    return story


def build_education(cv_data, styles) -> list:
    story = []
    try:
        education = safe_list(getattr(cv_data, "education", None))
        if not education:
            return story

        story.append(Paragraph("Education", styles["SectionHeading"]))

        for edu in education:
            section = []
            try:
                degree = safe_text(getattr(edu, "degree", None))
                field  = safe_text(getattr(edu, "field_of_study", None))
                label  = f"{degree} in {field}" if degree and field else degree or field or "Degree not specified"

                deg_para = safe_paragraph(label, styles["JobTitle"])
                if deg_para:
                    section.append(deg_para)

                inst = safe_text(getattr(edu, "institution", None))
                if inst:
                    inst_para = safe_paragraph(inst, styles["CompanyName"])
                    if inst_para:
                        section.append(inst_para)

                grad_year = getattr(edu, "graduation_year", None)
                if grad_year:
                    yr_para = safe_paragraph(f"Graduated: {grad_year}", styles["DateRange"])
                    if yr_para:
                        section.append(yr_para)

                if section:
                    story.append(KeepTogether(section))
                    story.append(Spacer(1, 0.1 * inch))

            except Exception as e:
                print(f"⚠️ Skipping malformed education entry: {e}")
                continue

    except Exception as e:
        print(f"⚠️ Education section failed: {e}")
    return story


def build_certifications(cv_data, styles) -> list:
    story = []
    try:
        certs = safe_list(getattr(cv_data, "certifications", None))
        if not certs:
            return story

        story.append(Paragraph("Certifications", styles["SectionHeading"]))

        for cert in certs:
            try:
                name   = safe_text(getattr(cert, "name",   None), "Unnamed Certification")
                issuer = safe_text(getattr(cert, "issuer", None))
                year   = getattr(cert, "year", None)

                line = name
                if issuer:
                    line += f" — {issuer}"
                if year:
                    line += f" ({year})"

                para = safe_paragraph(line, styles["BulletPoint"])
                if para:
                    story.append(para)

            except Exception as e:
                print(f"⚠️ Skipping malformed certification: {e}")
                continue

    except Exception as e:
        print(f"⚠️ Certifications section failed: {e}")
    return story


def build_projects(cv_data, styles) -> list:
    story = []
    try:
        projects = safe_list(getattr(cv_data, "projects", None))
        if not projects:
            return story

        story.append(Paragraph("Projects", styles["SectionHeading"]))

        for project in projects:
            section = []
            try:
                title = safe_text(getattr(project, "title", None), "Untitled Project")
                title_para = safe_paragraph(title, styles["JobTitle"])
                if title_para:
                    section.append(title_para)

                techs = safe_list(getattr(project, "technologies", None))
                techs = [clean_unicode(safe_text(t)) for t in techs if t]
                if techs:
                    tech_para = safe_paragraph(
                        "<i>Technologies:</i> " + ", ".join(techs),
                        styles["DateRange"]
                    )
                    if tech_para:
                        section.append(tech_para)

                desc = getattr(project, "description", None)
                if desc:
                    desc_para = safe_paragraph(safe_text(desc), styles["BulletPoint"])
                    if desc_para:
                        section.append(desc_para)

                if section:
                    story.append(KeepTogether(section))
                    story.append(Spacer(1, 0.1 * inch))

            except Exception as e:
                print(f"⚠️ Skipping malformed project entry: {e}")
                continue

    except Exception as e:
        print(f"⚠️ Projects section failed: {e}")
    return story


# ============================================================
# MAIN PDF FUNCTION
# ============================================================

def create_cv_pdf(cv_data, output_filename="optimized_cv.pdf"):
    """
    Generate a PDF from a CV data object.
    Never crashes — each section is isolated.
    Returns output_filename on success, None on total failure.
    """

    # ← CHANGED: guard against completely missing cv_data or meta
    if not cv_data:
        print("❌ Cannot generate PDF: cv_data is None.")
        return None

    if not getattr(cv_data, "meta", None):
        print("❌ Cannot generate PDF: cv_data.meta is missing.")
        return None

    try:
        doc = SimpleDocTemplate(
            output_filename,
            pagesize=letter,
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )

        styles = create_cv_styles()
        story  = []

        # ← CHANGED: each section is now a separate function call
        # If one section fails internally it prints a warning and returns []
        # The rest of the PDF still builds fine
        story += build_header(cv_data, styles)
        story += build_summary(cv_data, styles)
        story += build_skills(cv_data, styles)
        story += build_experience(cv_data, styles)
        story += build_education(cv_data, styles)
        story += build_certifications(cv_data, styles)
        story += build_projects(cv_data, styles)

        if not story:
            print("⚠️ No content to render in PDF.")
            return None

        doc.build(story)
        print(f"\n✓ CV PDF created successfully: {output_filename}")
        return output_filename

    except Exception as e:
        print(f"❌ PDF generation failed: {e}")
        return None