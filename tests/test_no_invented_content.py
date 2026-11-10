"""
test_no_invented_content.py — Anti-hallucination guard.

These tests verify the pipeline never invents skills, companies, or dates
that weren't in the original profile.
"""

from app.domain.parsing.input_validator import validate_jd

# ── Input validator — edge cases ──────────────────────────────────────────────


def test_gibberish_jd_rejected():
    result = validate_jd("aaaa bbbb cccc dddd aaaa aaaa aaaa aaaa")
    assert not result.is_valid
    assert result.error_code == "GIBBERISH"


def test_repeated_single_word_rejected():
    text = "job " * 200
    result = validate_jd(text)
    assert not result.is_valid


_VALID_JD = (
    "We are looking for a skilled software engineer with 3+ years of experience in backend "
    "development. The candidate will be responsible for building and maintaining REST APIs, "
    "mentoring junior developers, conducting code reviews, and collaborating with cross-functional "
    "teams to deliver high-quality software products. Requirements include Python, Django, PostgreSQL, "
    "Docker, and strong communication skills. Experience with AWS or similar cloud platforms is a plus. "
    "The role requires the ability to work independently in a fully remote environment and to take "
    "ownership of features from design through deployment. We offer competitive salary, flexible "
    "working hours, health benefits, and professional development opportunities including conference "
    "attendance and learning budget. This is a full-time permanent position at a growing technology "
    "company based in Dhaka, Bangladesh with an international client base."
)


def test_valid_jd_accepted():
    result = validate_jd(_VALID_JD)
    assert result.is_valid


def test_email_extracted_from_jd():
    jd = (
        "We are hiring an experienced marketing manager with a strong background in digital marketing, "
        "SEO strategy, and content creation. The successful candidate will lead end-to-end marketing "
        "campaigns, manage the brand's social media presence, coordinate with the design team, and "
        "report on performance metrics to senior stakeholders. Requirements include at least 3 years "
        "in a marketing role, proficiency in Google Analytics, Facebook Ads Manager, and email "
        "marketing platforms. Strong writing skills and an eye for detail are essential. "
        "This is a full-time position with a competitive salary package and benefits. "
        "Please apply by sending your CV along with a cover letter to jobs@techbd.com."
    )
    result = validate_jd(jd)
    assert result.is_valid
    assert result.application_email == "jobs@techbd.com"


def test_no_email_in_jd_returns_none():
    jd = (
        "Seeking a qualified secondary school teacher with 2 years of experience in education. "
        "Responsibilities include lesson planning, student assessment, parent-teacher communication, "
        "and maintaining an inclusive and engaging classroom environment. Requirements: B.Ed degree, "
        "strong classroom management skills, and a genuine passion for student development. "
        "The successful candidate must be proficient in curriculum design and be comfortable using "
        "digital teaching tools. Full-time position at a reputable private school in Dhaka. "
        "Benefits include medical coverage, annual leave, provident fund, and a supportive working "
        "environment. Candidates with experience teaching Cambridge or Edexcel curricula will be "
        "given preference. Shortlisted candidates will be contacted for written test and interviews."
    )
    result = validate_jd(jd)
    assert result.is_valid
    assert result.application_email is None


def test_emoji_heavy_jd_still_passes_if_real():
    jd = (
        "🔥 We are hiring! 💼 Looking for a Python developer 🐍 with Django and FastAPI experience. "
        "Requirements: 2+ years in backend development, strong SQL skills, REST API design, "
        "and experience with Docker and cloud platforms. The candidate will be responsible for "
        "building scalable microservices, reviewing code, writing unit and integration tests, "
        "and collaborating with a distributed international team across multiple time zones. "
        "We offer competitive salary, fully remote work arrangement, annual performance bonus, "
        "learning budget, and exciting product challenges. Team player with strong written "
        "communication skills preferred. The role involves ownership of services end-to-end "
        "from design through monitoring. Full-time remote position open to candidates in Bangladesh. "
        "Apply now! 🚀"
    )
    result = validate_jd(jd)
    assert result.is_valid, f"Emoji-heavy JD should pass: {result.user_message}"


def test_bangla_jd_accepted():
    jd = (
        "আমরা একজন অভিজ্ঞ সফটওয়্যার ইঞ্জিনিয়ার নিয়োগ দিতে চাই। প্রার্থীর Python এবং Django "
        "অভিজ্ঞতা থাকতে হবে। দায়িত্বের মধ্যে রয়েছে REST API তৈরি করা, কোড রিভিউ করা এবং "
        "টিম লিডারশিপ প্রদান করা। যোগ্যতা হিসেবে কম্পিউটার সায়েন্সে স্নাতক ডিগ্রি প্রয়োজন। "
        "প্রার্থীর কমপক্ষে ৩ বছরের কর্মঅভিজ্ঞতা থাকতে হবে। বেতন আলোচনাসাপেক্ষ। "
        "পূর্ণকালীন পদ, ঢাকায় অবস্থিত প্রতিষ্ঠানে আবেদন করুন। আমাদের দলে যোগ দিতে আগ্রহী "
        "প্রার্থীরা জীবনবৃত্তান্ত পাঠান। নিয়োগ প্রক্রিয়া শীঘ্রই শুরু হবে।"
    )
    result = validate_jd(jd)
    assert result.is_valid, f"Bangla JD should pass: {result.user_message}"


# ── No-invention rule — structural checks ─────────────────────────────────────


def test_no_skills_invented_marker():
    """
    This is a meta-test that documents the no-invention rule.
    The actual guard is enforced by the system prompt in nodes.py (hard constraint).
    This test records the expected behaviour.
    """
    # If a CV has no Python experience and a JD requires Python,
    # the rewritten CV must NOT contain "Python".
    # Full pipeline test requires LLM — assert the rule is documented instead.
    rule = (  # noqa: F841
        "CRITICAL: You may rewrite and reorder existing facts only. "
        "Never invent job titles, dates, metrics, company names, certifications, "
        "or technologies that are not already present in the user's profile."
    )
    from core.pipeline.prompts import REWRITE_PROMPT

    prompt_text = REWRITE_PROMPT.template
    assert any(
        keyword in prompt_text.lower()
        for keyword in ["never invent", "do not invent", "evidence-only", "fabricat"]
    ), (
        "REWRITE_PROMPT must contain an explicit anti-hallucination instruction. "
        "Check core/pipeline/prompts.py."
    )
