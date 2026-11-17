"""Verifier severity and the next step after a trust check (E4, D3)."""

from collections.abc import Iterable
from typing import Literal

from app.domain.trust.report import ClaimKind, TrustReport, TrustStatus, UnsupportedClaim

# Hard claims force one revise; skills are soft because they surface from bullets and answers.
HARD_KINDS: frozenset[ClaimKind] = frozenset(
    {"employer", "title", "degree", "institution", "certification", "licence", "number", "date"}
)

NextAction = Literal["accept", "revise", "finish_with_flags"]


def severity_of(kind: ClaimKind) -> Literal["hard", "soft"]:
    return "hard" if kind in HARD_KINDS else "soft"


def status_for(claims: Iterable[UnsupportedClaim]) -> TrustStatus:
    severities = {c.severity for c in claims}
    if "hard" in severities:
        return "fail"
    return "warn" if severities else "pass"


def next_action(report: TrustReport) -> NextAction:
    """A failing report is revised once; still failing after that, the job finishes flagged (D3)."""
    if report.status != "fail":
        return "accept"
    return "finish_with_flags" if report.revised else "revise"
