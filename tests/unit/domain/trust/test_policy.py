import pytest

from app.domain.trust.policy import HARD_KINDS, next_action, status_for
from app.domain.trust.report import SourceCounts, TrustReport, UnsupportedClaim


def _claim(kind: str, severity: str) -> UnsupportedClaim:
    return UnsupportedClaim.model_validate(
        {
            "text": "x",
            "section": "skills",
            "kind": kind,
            "reason": "not_in_source",
            "layer": "deterministic",
            "severity": severity,
        }
    )


def test_hard_kinds_follow_e4():
    assert HARD_KINDS == {
        "employer",
        "title",
        "degree",
        "institution",
        "certification",
        "licence",
        "number",
        "date",
    }


def test_status_for():
    assert status_for([]) == "pass"
    assert status_for([_claim("skill", "soft")]) == "warn"
    assert status_for([_claim("skill", "soft"), _claim("degree", "hard")]) == "fail"


@pytest.mark.parametrize(
    ("status", "revised", "action"),
    [
        ("pass", False, "accept"),
        ("pass", True, "accept"),
        ("warn", False, "accept"),
        ("warn", True, "accept"),
        ("fail", False, "revise"),
        ("fail", True, "finish_with_flags"),
    ],
)
def test_next_action(status: str, revised: bool, action: str):
    report = TrustReport.model_validate(
        {"status": status, "sources": SourceCounts(cv=0, answers=0), "revised": revised}
    )
    assert next_action(report) == action


def test_unsupported_claim_text_is_cut_to_200():
    long = UnsupportedClaim.model_validate(
        {**_claim("skill", "soft").model_dump(), "text": "a" * 500}
    )
    assert len(long.text) == 200
