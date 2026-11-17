"""Deterministic support check: each output claim must trace to the source CV or the answers."""

from collections import defaultdict
from decimal import Decimal
from typing import Literal

from app.domain.cv.rewrite import RewrittenCV
from app.domain.trust.aliases import skill_forms
from app.domain.trust.claims import (
    DATED_SECTIONS,
    NAME_FIELDS,
    Claim,
    SourceEvidence,
    extract_claims,
)
from app.domain.trust.fuzzy import token_set_ratio
from app.domain.trust.policy import severity_of
from app.domain.trust.report import SourceCounts, UnsupportedClaim

NAME_MATCH = 90
_MIN_SUBSTRING = 4  # shorter added tokens must appear as whole words

Support = Literal["cv", "answers"] | None
Reason = Literal["not_in_source", "number_not_in_source", "date_changed"]


def _has_phrase(text_norm: str, phrase: str) -> bool:
    return bool(phrase) and f" {phrase} " in f" {text_norm} "


def _token_in(token: str, text_norm: str) -> bool:
    return _has_phrase(text_norm, token) or (len(token) >= _MIN_SUBSTRING and token in text_norm)


def _name_support(claim: Claim, ev: SourceEvidence) -> Support:
    """A same-kind source name at >= NAME_MATCH whose added words the source also contains.

    The added-word check catches inflation that token-set similarity forgives: "Senior
    Engineer" against "Engineer", "MSc Nursing" against "BSc Nursing".
    """
    tokens = set(claim.norm.split())
    fallback: Support = None
    for src in ev.cv_claims:
        if src.kind != claim.kind or token_set_ratio(claim.norm, src.norm) < NAME_MATCH:
            continue
        added = tokens - set(src.norm.split())
        if all(_token_in(t, ev.cv_text_norm) for t in added):
            return "cv"
        if all(_token_in(t, ev.cv_text_norm) or _token_in(t, ev.answer_text_norm) for t in added):
            fallback = "answers"
    if fallback or _has_phrase(ev.answer_text_norm, claim.norm):
        return "answers"
    return None


def _skill_support(claim: Claim, ev: SourceEvidence) -> Support:
    if any(src.kind == "skill" and src.norm == claim.norm for src in ev.cv_claims):
        return "cv"
    forms = skill_forms(claim.norm)
    if any(_has_phrase(ev.cv_text_norm, f) for f in forms):
        return "cv"
    if any(_has_phrase(ev.answer_text_norm, f) for f in forms):
        return "answers"
    return None


def _number_support(claim: Claim, ev: SourceEvidence) -> Support:
    value = Decimal(claim.norm)
    if value in ev.cv_numbers:
        return "cv"
    return "answers" if value in ev.answer_numbers else None


def _support(claim: Claim, ev: SourceEvidence) -> Support:
    if claim.kind == "skill":
        return _skill_support(claim, ev)
    if claim.kind == "number":
        return _number_support(claim, ev)
    return _name_support(claim, ev)


def _entries(claims: list[Claim]) -> dict[str, list[Claim]]:
    grouped: dict[str, list[Claim]] = defaultdict(list)
    for claim in claims:
        if claim.section in DATED_SECTIONS and claim.entry_key is not None:
            grouped[claim.entry_key].append(claim)
    return grouped


def _names(entry: list[Claim]) -> list[str | None]:
    """Organisation then role, in NAME_FIELDS order (None where the entry has no such name)."""
    kinds = NAME_FIELDS[entry[0].section].values()
    by_kind: dict[str, str] = {c.kind: c.norm for c in entry if c.kind != "date"}
    return [by_kind.get(kind) for kind in kinds]


def _pair_score(out: list[Claim], src: list[Claim]) -> tuple[int, int]:
    """(anchor score, role score); the anchor is the organisation, or the role when unnamed."""
    (out_org, out_role), (src_org, src_role) = _names(out), _names(src)
    role = token_set_ratio(out_role or "", src_role or "")
    if out_org and src_org:
        return token_set_ratio(out_org, src_org), role
    return (role, 0) if not out_org and not src_org else (0, 0)


def _date_claims(
    out_entries: dict[str, list[Claim]], src_entries: dict[str, list[Claim]]
) -> tuple[list[UnsupportedClaim], int]:
    flagged: list[UnsupportedClaim] = []
    supported = 0
    for entry in out_entries.values():
        section = entry[0].section
        candidates = [e for e in src_entries.values() if e[0].section == section]
        scored = [(_pair_score(entry, src), src) for src in candidates]
        scored = [(score, src) for score, src in scored if score[0] >= NAME_MATCH]
        if not scored:
            continue  # unmatched entry: its organisation claim is already checked
        source = max(scored, key=lambda pair: pair[0])[1]
        source_dates = {c.norm.split(":")[0]: c for c in source if c.kind == "date"}
        label = next((name for name in _names(entry) if name), "")
        for claim in (c for c in entry if c.kind == "date"):
            if source_dates.get(claim.norm.split(":")[0], claim).norm == claim.norm:
                supported += 1
                continue
            text = f"{label}: {claim.text}" if label else claim.text
            flagged.append(_unsupported(claim, "date_changed", text))
    return flagged, supported


def _unsupported(
    claim: Claim,
    reason: Reason,
    text: str | None = None,
) -> UnsupportedClaim:
    return UnsupportedClaim(
        text=text or claim.text,
        section=claim.section,
        kind=claim.kind,
        reason=reason,
        layer="deterministic",
        severity=severity_of(claim.kind),
    )


def find_unsupported(
    evidence: SourceEvidence, output: RewrittenCV
) -> tuple[list[UnsupportedClaim], SourceCounts]:
    """Claims in the output with no support, and how many were supported by the CV or answers."""
    claims = extract_claims(output)
    flagged: list[UnsupportedClaim] = []
    counts = {"cv": 0, "answers": 0}
    for claim in claims:
        if claim.kind == "date":
            continue
        support = _support(claim, evidence)
        if support is None:
            reason: Reason = "number_not_in_source" if claim.kind == "number" else "not_in_source"
            flagged.append(_unsupported(claim, reason))
        else:
            counts[support] += 1
    dates, supported = _date_claims(_entries(claims), _entries(evidence.cv_claims))
    return [*flagged, *dates], SourceCounts(cv=counts["cv"] + supported, answers=counts["answers"])
