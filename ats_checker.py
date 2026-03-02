# ==========================================================
# ATS CHECKER — Realistic Dumb ATS Simulation
# ==========================================================

import re


# ----------------------------------------------------------
# Basic Utilities
# ----------------------------------------------------------

def normalize(text):
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)
    return re.sub(r"\s+", " ", text.lower().strip())


def tokenize(text: str):
    return set(re.findall(r"\b[a-z0-9\+\#\.]+\b", normalize(text)))


def normalize_set(items):
    return set(normalize(i) for i in items if i)


def safe_div(n, d):
    return round(n / d * 100, 2) if d else 0.0


def token_overlap(a: str, b: str) -> bool:
    """Return True if two phrases share at least one token."""
    return len(tokenize(a) & tokenize(b)) > 0


def flexible_match(a: str, b: str) -> bool:
    """
    Simulate realistic dumb ATS:
    - substring match both directions
    - OR token overlap
    """
    a_norm = normalize(a)
    b_norm = normalize(b)

    return (
        a_norm in b_norm or
        b_norm in a_norm or
        token_overlap(a_norm, b_norm)
    )


# ----------------------------------------------------------
# Must-Have Matching
# ----------------------------------------------------------

def match_must_haves(jd, cv):

    cv_items = (
        cv.skills.hard_skills +
        cv.skills.tools +
        cv.skills.frameworks +
        cv.skills.cloud_platforms
    )

    matched = []
    missing = []

    for req in jd.requirements.must_have:
        found = False
        for skill in cv_items:
            if flexible_match(req, skill):
                found = True
                break

        if found:
            matched.append(req)
        else:
            missing.append(req)

    score = safe_div(len(matched), len(jd.requirements.must_have))

    return {
        "score": score,
        "matched": matched,
        "missing": missing
    }


# ----------------------------------------------------------
# Skills Matching (Improved)
# ----------------------------------------------------------

def match_skills(jd, cv):

    jd_skills = jd.skills.hard_skills
    cv_skills = cv.skills.hard_skills

    matched = []
    missing = []

    for jd_skill in jd_skills:
        found = False
        for cv_skill in cv_skills:
            if flexible_match(jd_skill, cv_skill):
                found = True
                break

        if found:
            matched.append(jd_skill)
        else:
            missing.append(jd_skill)

    score = safe_div(len(matched), len(jd_skills))

    return {
        "score": score,
        "matched": matched,
        "missing": missing
    }


# ----------------------------------------------------------
# Experience Matching (Kept Same)
# ----------------------------------------------------------

def match_experience(jd, cv):

    score = 100

    if jd.experience.min_years and cv.experience_summary.total_years:
        if cv.experience_summary.total_years < jd.experience.min_years:
            score -= 30

    if jd.experience.seniority != cv.experience_summary.seniority:
        score -= 10

    return {
        "score": max(score, 0),
        "jd_required_years": jd.experience.min_years,
        "cv_years": cv.experience_summary.total_years,
        "jd_seniority": jd.experience.seniority,
        "cv_seniority": cv.experience_summary.seniority
    }


# ----------------------------------------------------------
# Tools Matching (Improved)
# ----------------------------------------------------------

def match_tools(jd, cv):

    jd_tools = jd.skills.tools + jd.skills.cloud_platforms
    cv_tools = cv.skills.tools + cv.skills.cloud_platforms

    matched = []
    missing = []

    for jd_tool in jd_tools:
        found = False
        for cv_tool in cv_tools:
            if flexible_match(jd_tool, cv_tool):
                found = True
                break

        if found:
            matched.append(jd_tool)
        else:
            missing.append(jd_tool)

    score = safe_div(len(matched), len(jd_tools))

    return {
        "score": score,
        "matched": matched,
        "missing": missing
    }


# ----------------------------------------------------------
# Education Matching (Slightly Improved)
# ----------------------------------------------------------

def match_education(jd, cv):

    jd_fields = jd.education.fields_of_study
    cv_fields = [e.field_of_study for e in cv.education]

    matched = any(
        flexible_match(jd_field, cv_field)
        for jd_field in jd_fields
        for cv_field in cv_fields
    )

    score = 100 if matched else 50

    return {
        "score": score,
        "jd_fields": jd_fields,
        "cv_fields": cv_fields
    }


# ----------------------------------------------------------
# Responsibilities Matching (Token Based)
# ----------------------------------------------------------

def match_responsibilities(jd, cv):

    jd_resp = jd.responsibilities.responsibilities

    cv_resp = [
        r
        for exp in cv.work_experience
        for r in exp.responsibilities
    ]

    matched = []

    for jd_item in jd_resp:
        for cv_item in cv_resp:
            if flexible_match(jd_item, cv_item):
                matched.append(jd_item)
                break

    score = safe_div(len(matched), len(jd_resp))

    return {
        "score": score,
        "matched": matched
    }


# ----------------------------------------------------------
# Final Weighted Score
# ----------------------------------------------------------

def compute_final_match(jd, cv):

    must_have = match_must_haves(jd, cv)
    skills = match_skills(jd, cv)
    experience = match_experience(jd, cv)
    tools = match_tools(jd, cv)
    education = match_education(jd, cv)
    responsibilities = match_responsibilities(jd, cv)

    final_score = (
        must_have["score"] * 0.15 +
        skills["score"] * 0.35 +
        experience["score"] * 0.25 +
        tools["score"] * 0.10 +
        education["score"] * 0.10 +
        responsibilities["score"] * 0.05
    )

    return {
        "overall_score": round(final_score, 2),
        "section_scores": {
            "must_have": must_have,
            "skills": skills,
            "experience": experience,
            "tools": tools,
            "education": education,
            "responsibilities": responsibilities
        },
        "hard_gaps": must_have["missing"],
        "rewrite_hints": {
            "title_alignment": f"{cv.experience_summary.role_type} → {jd.job_title}",
            "missing_tools": tools["missing"]
        }
    }