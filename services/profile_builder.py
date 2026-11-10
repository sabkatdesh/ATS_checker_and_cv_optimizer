"""
ProfileBuilder — converts a profile dict (from cv_profiles table) to resume text.

Two entry points:
  ProfileBuilder.from_profile_dict(profile, domain)  → plain text string
  ProfileBuilder.detect_domain(profile)              → Domain enum value

Block rendering follows DOMAIN_BLOCK_ORDER so section order matches the PDF renderer.
Empty blocks are silently skipped — no "LICENSES\n(none)" headings.
"""
from __future__ import annotations

from core.schemas.domain_config import Domain, DOMAIN_BLOCK_ORDER, get_block_order


class ProfileBuilder:

    # ── Public API ──────────────────────────────────────────────────────────────

    @classmethod
    def from_profile_dict(cls, profile: dict, domain: Domain | str | None = None) -> str:
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
            renderer = cls._RENDERERS.get(block)
            if renderer:
                renderer(p, lines)

        # References line at very end when flag is set
        if p.get("references_available"):
            lines.append("")
            lines.append("References available upon request.")

        return "\n".join(lines)

    @classmethod
    def detect_domain(cls, profile: dict) -> Domain:
        """
        Heuristic domain classification from profile fields.
        Used when the user has not explicitly selected a domain.
        """
        p = cls._normalise_keys(profile)

        text_corpus = cls._build_search_corpus(p).lower()
        licenses = [str(lic).lower() for lic in (p.get("licenses") or [])]
        license_text = " ".join(licenses)

        # Medical — licenses/registrations are the strongest signal
        medical_signals = [
            "bnmc", "bmc", "bmdc", "mbbs", " md ", "registered nurse",
            " rn ", "physician", "surgeon", "clinical", "ward", "hospital",
            "patient", "diagnosis", "nursing",
        ]
        if any(s in license_text or s in text_corpus for s in medical_signals):
            return Domain.MEDICAL

        # Trades — trade qualification keywords
        trades_signals = [
            "electrician", "electrical", "plumber", "plumbing", "welder",
            "welding", "carpenter", "bteb", "nc-3", "nc3", "nvq", "construction",
            "mechanic", "hvac", "refrigeration",
        ]
        if any(s in license_text or s in text_corpus for s in trades_signals):
            return Domain.TRADES

        # Education — academic keywords
        education_signals = [
            "teacher", "lecturer", "professor", "phd", "thesis", "syllabus",
            "curriculum", "pedagogy", "instruction", "classroom", "faculty",
            "publication", "journal", "research paper",
        ]
        if any(s in text_corpus for s in education_signals):
            return Domain.EDUCATION

        # Legal
        legal_signals = [
            "advocate", "attorney", "barrister", "solicitor", "llb", "llm",
            "bar council", "law chamber", "litigation", "legal counsel",
        ]
        if any(s in text_corpus for s in legal_signals):
            return Domain.LEGAL

        # Finance
        finance_signals = [
            "cfa", "cpa", "acca", "chartered accountant", "financial analyst",
            "investment", "banking", "audit", "tax", "balance sheet", "ledger",
            "portfolio management", "equity", "fixed income",
        ]
        if any(s in text_corpus for s in finance_signals):
            return Domain.FINANCE

        # Creative
        creative_signals = [
            "designer", "ui/ux", "ux designer", "ui designer", "graphic design",
            "illustrator", "photoshop", "figma", "branding", "typography",
            "video editor", "motion graphic", "art director", "copywriter",
        ]
        if any(s in text_corpus for s in creative_signals):
            return Domain.CREATIVE

        # Tech — checked last because tech words appear in many domains
        tech_signals = [
            "python", "javascript", "typescript", "java", "golang", "rust",
            "react", "angular", "vue", "node.js", "django", "fastapi",
            "aws", "azure", "gcp", "docker", "kubernetes", "devops",
            "machine learning", "deep learning", "data science", "sql",
            "postgresql", "mongodb", "redis", "api", "backend", "frontend",
            "software engineer", "developer",
        ]
        if any(s in text_corpus for s in tech_signals):
            return Domain.TECH

        return Domain.GENERAL

    # ── Internal helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_domain(profile: dict, domain: Domain | str | None) -> Domain:
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
    def _normalise_keys(profile: dict) -> dict:
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
    def _build_search_corpus(p: dict) -> str:
        """Flatten relevant profile fields into a single searchable string."""
        parts: list[str] = []
        for key in ("professional_summary", "skills", "work_experience", "education",
                    "certifications", "publications", "trade_qualifications"):
            val = p.get(key)
            if val:
                parts.append(str(val))
        return " ".join(parts)

    # ── Block renderers (one per block name) ────────────────────────────────────

    @staticmethod
    def _render_meta(p: dict, lines: list[str]) -> None:
        if p.get("full_name"):
            lines.append(p["full_name"])
        if p.get("email"):
            lines.append(f"Email: {p['email']}")
        if p.get("phone"):
            lines.append(f"Phone: {p['phone']}")
        if p.get("location"):
            lines.append(f"Location: {p['location']}")
        if p.get("linkedin"):
            lines.append(f"LinkedIn: {p['linkedin']}")
        # Support both old 'github'/'portfolio' keys and new 'optional_links' dict
        if p.get("github"):
            lines.append(f"GitHub: {p['github']}")
        if p.get("portfolio"):
            lines.append(f"Portfolio: {p['portfolio']}")
        if p.get("optional_links"):
            for label, url in p["optional_links"].items():
                if label.lower() not in ("github", "portfolio", "linkedin"):
                    lines.append(f"{label}: {url}")
        lines.append("")

    @staticmethod
    def _render_professional_summary(p: dict, lines: list[str]) -> None:
        val = p.get("professional_summary")
        if val:
            lines.append("PROFESSIONAL SUMMARY")
            lines.append(val)
            lines.append("")

    @staticmethod
    def _render_skills(p: dict, lines: list[str]) -> None:
        skills = p.get("skills") or {}
        if not skills:
            return
        lines.append("SKILLS")
        if skills.get("hard_skills"):
            lines.append(f"Hard Skills: {', '.join(skills['hard_skills'])}")
        if skills.get("tools"):
            lines.append(f"Tools: {', '.join(skills['tools'])}")
        if skills.get("frameworks"):
            lines.append(f"Frameworks: {', '.join(skills['frameworks'])}")
        if skills.get("cloud_platforms"):
            lines.append(f"Cloud: {', '.join(skills['cloud_platforms'])}")
        if skills.get("soft_skills"):
            lines.append(f"Soft Skills: {', '.join(skills['soft_skills'])}")
        lines.append("")

    @staticmethod
    def _render_work_experience(p: dict, lines: list[str]) -> None:
        experience = p.get("work_experience") or []
        if not experience:
            return
        lines.append("WORK EXPERIENCE")
        for exp in experience:
            title = exp.get("job_title") or exp.get("title", "")
            company = exp.get("company_name") or exp.get("company", "")
            if title and company:
                lines.append(f"{title} at {company}")
            elif title:
                lines.append(title)

            start = exp.get("start_date", "")
            end = exp.get("end_date") or "Present"
            if start:
                lines.append(f"{start} - {end}")

            emp_type = exp.get("employment_type")
            if emp_type:
                lines.append(f"Type: {emp_type}")

            for r in (exp.get("responsibilities") or []):
                lines.append(f"- {r}")
            for a in (exp.get("achievements") or []):
                lines.append(f"+ {a}")
            for t in (exp.get("tools_used") or []):
                pass  # tools used listed inline if needed; skip heading
            lines.append("")

    @staticmethod
    def _render_education(p: dict, lines: list[str]) -> None:
        education = p.get("education") or []
        if not education:
            return
        lines.append("EDUCATION")
        for edu in education:
            degree = edu.get("degree", "")
            field = edu.get("field_of_study") or edu.get("field", "")
            institution = edu.get("institution", "")
            if degree and field:
                lines.append(f"{degree} in {field}")
            elif degree:
                lines.append(degree)
            if institution:
                lines.append(institution)
            if edu.get("graduation_year"):
                lines.append(f"Graduated: {edu['graduation_year']}")
            if edu.get("grade"):
                lines.append(f"Grade: {edu['grade']}")
            lines.append("")

    @staticmethod
    def _render_certifications(p: dict, lines: list[str]) -> None:
        certs = p.get("certifications") or []
        if not certs:
            return
        lines.append("CERTIFICATIONS")
        for cert in certs:
            line = cert.get("name", "")
            if cert.get("issuer"):
                line += f" — {cert['issuer']}"
            if cert.get("year"):
                line += f" ({cert['year']})"
            if cert.get("credential_id"):
                line += f" [ID: {cert['credential_id']}]"
            lines.append(line)
        lines.append("")

    @staticmethod
    def _render_projects(p: dict, lines: list[str]) -> None:
        projects = p.get("projects") or []
        if not projects:
            return
        lines.append("PROJECTS")
        for proj in projects:
            lines.append(proj.get("title", ""))
            if proj.get("description"):
                lines.append(proj["description"])
            if proj.get("technologies"):
                lines.append(f"Tech: {', '.join(proj['technologies'])}")
            if proj.get("url"):
                lines.append(f"URL: {proj['url']}")
            lines.append("")

    @staticmethod
    def _render_publications(p: dict, lines: list[str]) -> None:
        pubs = p.get("publications") or []
        if not pubs:
            return
        lines.append("PUBLICATIONS")
        for pub in pubs:
            line = pub.get("title", "")
            if pub.get("journal_or_venue"):
                line += f" — {pub['journal_or_venue']}"
            if pub.get("year"):
                line += f" ({pub['year']})"
            if pub.get("authors"):
                lines.append(f"Authors: {pub['authors']}")
            lines.append(line)
            if pub.get("doi_or_url"):
                lines.append(f"DOI/URL: {pub['doi_or_url']}")
            lines.append("")

    @staticmethod
    def _render_licenses(p: dict, lines: list[str]) -> None:
        licenses = p.get("licenses") or []
        if not licenses:
            return
        lines.append("LICENSES & REGISTRATIONS")
        for lic in licenses:
            line = lic.get("name", "")
            if lic.get("issuing_body"):
                line += f" — {lic['issuing_body']}"
            if lic.get("license_number"):
                line += f" [#{lic['license_number']}]"
            if lic.get("valid_until"):
                line += f" (Valid until: {lic['valid_until']})"
            lines.append(line)
        lines.append("")

    @staticmethod
    def _render_clinical_practice(p: dict, lines: list[str]) -> None:
        clinical = p.get("clinical_practice") or []
        if not clinical:
            return
        lines.append("CLINICAL PRACTICE")
        for entry in clinical:
            setting = entry.get("setting", "")
            role = entry.get("role", "")
            institution = entry.get("institution", "")
            if role and institution:
                lines.append(f"{role} — {institution} ({setting})")
            elif setting:
                lines.append(setting)

            start = entry.get("start_date", "")
            end = entry.get("end_date") or "Present"
            if start:
                lines.append(f"{start} - {end}")
            for r in (entry.get("responsibilities") or []):
                lines.append(f"- {r}")
            lines.append("")

    @staticmethod
    def _render_trade_qualifications(p: dict, lines: list[str]) -> None:
        quals = p.get("trade_qualifications") or []
        if not quals:
            return
        lines.append("TRADE QUALIFICATIONS")
        for q in quals:
            line = q.get("qualification", "")
            if q.get("certifying_body"):
                line += f" — {q['certifying_body']}"
            if q.get("year"):
                line += f" ({q['year']})"
            lines.append(line)
        lines.append("")

    @staticmethod
    def _render_languages(p: dict, lines: list[str]) -> None:
        langs = p.get("languages") or []
        if not langs:
            return
        lines.append("LANGUAGES")
        for lang in langs:
            line = lang.get("language", "")
            if lang.get("proficiency"):
                line += f" ({lang['proficiency']})"
            lines.append(line)
        lines.append("")

    @staticmethod
    def _render_volunteering(p: dict, lines: list[str]) -> None:
        vols = p.get("volunteering") or []
        if not vols:
            return
        lines.append("VOLUNTEERING")
        for v in vols:
            org = v.get("organization", "")
            role = v.get("role", "")
            if role and org:
                lines.append(f"{role} at {org}")
            elif org:
                lines.append(org)
            if v.get("description"):
                lines.append(v["description"])
            lines.append("")

    @staticmethod
    def _render_awards(p: dict, lines: list[str]) -> None:
        awards = p.get("awards") or []
        if not awards:
            return
        lines.append("AWARDS & HONOURS")
        for award in awards:
            line = award.get("title", "")
            if award.get("issuer"):
                line += f" — {award['issuer']}"
            if award.get("year"):
                line += f" ({award['year']})"
            lines.append(line)
            if award.get("description"):
                lines.append(award["description"])
        lines.append("")

    # Map block names to renderer methods
    _RENDERERS = {
        "meta":                  _render_meta.__func__,
        "professional_summary":  _render_professional_summary.__func__,
        "skills":                _render_skills.__func__,
        "work_experience":       _render_work_experience.__func__,
        "education":             _render_education.__func__,
        "certifications":        _render_certifications.__func__,
        "projects":              _render_projects.__func__,
        "publications":          _render_publications.__func__,
        "licenses":              _render_licenses.__func__,
        "clinical_practice":     _render_clinical_practice.__func__,
        "trade_qualifications":  _render_trade_qualifications.__func__,
        "languages":             _render_languages.__func__,
        "volunteering":          _render_volunteering.__func__,
        "awards":                _render_awards.__func__,
    }


# ── Compatibility shim for old callers ──────────────────────────────────────────

def profile_to_resume_text(profile: dict) -> str:
    """Legacy wrapper. New code should call ProfileBuilder.from_profile_dict()."""
    return ProfileBuilder.from_profile_dict(profile)
