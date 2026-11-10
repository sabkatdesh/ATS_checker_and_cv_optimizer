"""
ATS checker — realistic dumb ATS simulation with 6 weighted sub-scores.

Usage (functional — backward compatible):
    from core.ats.ats_checker import compute_final_match
    result = compute_final_match(jd, cv)

Usage (class):
    checker = ATSChecker()
    result = checker.compute(jd, cv)
"""
from __future__ import annotations

import re


# ── Utilities ─────────────────────────────────────────────────────────────────────

def _normalize(text) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text).lower().strip())


def _tokenize(text: str) -> set:
    return set(re.findall(r"\b[a-z0-9\+\#\.]+\b", _normalize(text)))


def _safe_div(n: int, d: int) -> float:
    return round(n / d * 100, 2) if d else 0.0


def _token_overlap(a: str, b: str) -> bool:
    return len(_tokenize(a) & _tokenize(b)) > 0


def _flexible_match(a: str, b: str) -> bool:
    """Substring match in either direction OR token overlap."""
    a_n, b_n = _normalize(a), _normalize(b)
    return a_n in b_n or b_n in a_n or _token_overlap(a_n, b_n)


# ── Sub-score functions ───────────────────────────────────────────────────────────

def _match_must_haves(jd, cv) -> dict:
    cv_items = (
        cv.skills.hard_skills + cv.skills.tools
        + cv.skills.frameworks + cv.skills.cloud_platforms
    )
    matched, missing = [], []
    for req in jd.requirements.must_have:
        if any(_flexible_match(req, s) for s in cv_items):
            matched.append(req)
        else:
            missing.append(req)
    return {"score": _safe_div(len(matched), len(jd.requirements.must_have)),
            "matched": matched, "missing": missing}


def _match_skills(jd, cv) -> dict:
    matched, missing = [], []
    for jd_s in jd.skills.hard_skills:
        if any(_flexible_match(jd_s, cv_s) for cv_s in cv.skills.hard_skills):
            matched.append(jd_s)
        else:
            missing.append(jd_s)
    return {"score": _safe_div(len(matched), len(jd.skills.hard_skills)),
            "matched": matched, "missing": missing}


def _match_experience(jd, cv) -> dict:
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
        "cv_seniority": cv.experience_summary.seniority,
    }


def _match_tools(jd, cv) -> dict:
    jd_tools = jd.skills.tools + jd.skills.cloud_platforms
    cv_tools = cv.skills.tools + cv.skills.cloud_platforms
    matched, missing = [], []
    for jd_t in jd_tools:
        if any(_flexible_match(jd_t, cv_t) for cv_t in cv_tools):
            matched.append(jd_t)
        else:
            missing.append(jd_t)
    return {"score": _safe_div(len(matched), len(jd_tools)),
            "matched": matched, "missing": missing}


def _match_education(jd, cv) -> dict:
    jd_fields = jd.education.fields_of_study
    cv_fields = [e.field_of_study for e in cv.education]
    matched = any(
        _flexible_match(jf, cf)
        for jf in jd_fields for cf in cv_fields
    )
    return {"score": 100 if matched else 50,
            "jd_fields": jd_fields, "cv_fields": cv_fields}


def _match_responsibilities(jd, cv) -> dict:
    jd_resp = jd.responsibilities.responsibilities
    cv_resp = [r for exp in cv.work_experience for r in exp.responsibilities]
    matched = [jr for jr in jd_resp if any(_flexible_match(jr, cr) for cr in cv_resp)]
    return {"score": _safe_div(len(matched), len(jd_resp)), "matched": matched}


# ── Public API ────────────────────────────────────────────────────────────────────

def compute_final_match(jd, cv) -> dict:
    must_have = _match_must_haves(jd, cv)
    skills = _match_skills(jd, cv)
    experience = _match_experience(jd, cv)
    tools = _match_tools(jd, cv)
    education = _match_education(jd, cv)
    responsibilities = _match_responsibilities(jd, cv)

    final_score = (
        must_have["score"] * 0.15
        + skills["score"] * 0.35
        + experience["score"] * 0.25
        + tools["score"] * 0.10
        + education["score"] * 0.10
        + responsibilities["score"] * 0.05
    )

    return {
        "overall_score": round(final_score, 2),
        "section_scores": {
            "must_have": must_have, "skills": skills,
            "experience": experience, "tools": tools,
            "education": education, "responsibilities": responsibilities,
        },
        "hard_gaps": must_have["missing"],
        "rewrite_hints": {
            "title_alignment": f"{cv.experience_summary.role_type} -> {jd.job_title}",
            "missing_tools": tools["missing"],
        },
    }


class ATSChecker:
    """Class wrapper for dependency-injection use cases."""

    def compute(self, jd, cv) -> dict:
        return compute_final_match(jd, cv)
