"""Core block renderers: meta, summary, skills, work, education, certifications, projects."""

from __future__ import annotations

from typing import Any


def render_meta(p: dict[str, Any], lines: list[str]) -> None:
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


def render_professional_summary(p: dict[str, Any], lines: list[str]) -> None:
    val = p.get("professional_summary")
    if val:
        lines.append("PROFESSIONAL SUMMARY")
        lines.append(val)
        lines.append("")


def render_skills(p: dict[str, Any], lines: list[str]) -> None:
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


def render_work_experience(p: dict[str, Any], lines: list[str]) -> None:
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

        for r in exp.get("responsibilities") or []:
            lines.append(f"- {r}")
        for a in exp.get("achievements") or []:
            lines.append(f"+ {a}")
        for t in exp.get("tools_used") or []:  # noqa: B007
            pass  # tools used listed inline if needed; skip heading
        lines.append("")


def render_education(p: dict[str, Any], lines: list[str]) -> None:
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


def render_certifications(p: dict[str, Any], lines: list[str]) -> None:
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


def render_projects(p: dict[str, Any], lines: list[str]) -> None:
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
