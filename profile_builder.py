def profile_to_resume_text(profile: dict) -> str:
    """
    Input:  profile dict from cv_profiles table
    Output: plain text resume string
    """
    if not profile:
        return ""

    lines = []

    # ── Header ──────────────────────────────────────
    if profile.get("full_name"):
        lines.append(profile["full_name"])
    if profile.get("email"):
        lines.append(f"Email: {profile['email']}")
    if profile.get("phone"):
        lines.append(f"Phone: {profile['phone']}")
    if profile.get("location"):
        lines.append(f"Location: {profile['location']}")
    if profile.get("linkedin"):
        lines.append(f"LinkedIn: {profile['linkedin']}")
    if profile.get("github"):
        lines.append(f"GitHub: {profile['github']}")
    if profile.get("portfolio"):
        lines.append(f"Portfolio: {profile['portfolio']}")

    lines.append("")

    # ── Summary ─────────────────────────────────────
    if profile.get("summary"):
        lines.append("PROFESSIONAL SUMMARY")
        lines.append(profile["summary"])
        lines.append("")

    # ── Skills ──────────────────────────────────────
    skills = profile.get("skills") or {}
    if skills:
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

    # ── Experience ──────────────────────────────────
    experience = profile.get("experience") or []
    if experience:
        lines.append("WORK EXPERIENCE")
        for exp in experience:
            title = exp.get("job_title", "")
            company = exp.get("company", "")
            lines.append(f"{title} at {company}")

            start = exp.get("start_date", "")
            end = exp.get("end_date", "Present")
            if start:
                lines.append(f"{start} - {end}")

            for r in exp.get("responsibilities", []):
                lines.append(f"- {r}")
            for a in exp.get("achievements", []):
                lines.append(f"+ {a}")
            lines.append("")

    # ── Education ───────────────────────────────────
    education = profile.get("education") or []
    if education:
        lines.append("EDUCATION")
        for edu in education:
            degree = edu.get("degree", "")
            field = edu.get("field", "")
            institution = edu.get("institution", "")
            lines.append(f"{degree} in {field}")
            lines.append(institution)
            if edu.get("graduation_year"):
                lines.append(f"Graduated: {edu['graduation_year']}")
            lines.append("")

    # ── Projects ────────────────────────────────────
    projects = profile.get("projects") or []
    if projects:
        lines.append("PROJECTS")
        for proj in projects:
            lines.append(proj.get("title", ""))
            if proj.get("description"):
                lines.append(proj["description"])
            if proj.get("technologies"):
                lines.append(f"Tech: {', '.join(proj['technologies'])}")
            lines.append("")

    # ── Certifications ──────────────────────────────
    certs = profile.get("certifications") or []
    if certs:
        lines.append("CERTIFICATIONS")
        for cert in certs:
            line = cert.get("name", "")
            if cert.get("issuer"):
                line += f" — {cert['issuer']}"
            if cert.get("year"):
                line += f" ({cert['year']})"
            lines.append(line)

    return "\n".join(lines)