from app.domain.trust.judge import JudgeFinding, JudgeFindings, judge_claims


def _finding(issue: str = "fabrication", **kw: object) -> dict[str, object]:
    return {"section": "education", "output_text": "MBA", "issue": issue, "reason": "r", **kw}


def test_long_texts_are_cut_to_300():
    f = JudgeFinding.model_validate(_finding(output_text="x" * 400, reason="y" * 400))
    assert len(f.output_text) == 300 and len(f.reason) == 300


def test_only_the_first_20_findings_are_kept():
    many = JudgeFindings.model_validate(
        {"findings": [_finding(output_text=str(i)) for i in range(25)]}
    )
    assert [f.output_text for f in many.findings] == [str(i) for i in range(20)]


def test_fabrication_is_hard_and_inflation_soft():
    findings = JudgeFindings.model_validate(
        {"findings": [_finding(), _finding("inflation", section="work_experience")]}
    )
    claims = judge_claims(findings)
    assert [(c.layer, c.severity, c.kind, c.reason) for c in claims] == [
        ("judge", "hard", "statement", "not_in_source"),
        ("judge", "soft", "statement", "inflated"),
    ]
    assert [(c.section, c.text) for c in claims] == [
        ("education", "MBA"),
        ("work_experience", "MBA"),
    ]


def test_no_findings_is_the_default():
    assert JudgeFindings().findings == []
