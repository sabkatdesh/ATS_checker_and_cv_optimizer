"""Token-set similarity for names (employers, institutions, titles, credentials)."""

from difflib import SequenceMatcher

from app.domain.trust.normalise import normalise_text


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def token_set_ratio(a: str, b: str) -> int:
    """0-100: best ratio among the shared tokens and shared tokens plus each side's remainder.

    A name that is a token subset of the other scores 100 ("Dhaka Medical College" vs
    "Dhaka Medical College Hospital"); callers that must catch added words check those apart.
    """
    left, right = set(normalise_text(a).split()), set(normalise_text(b).split())
    if not left or not right:
        return 0
    common = " ".join(sorted(left & right))
    with_left = " ".join(filter(None, (common, " ".join(sorted(left - right)))))
    with_right = " ".join(filter(None, (common, " ".join(sorted(right - left)))))
    best = max(_ratio(common, with_left), _ratio(common, with_right), _ratio(with_left, with_right))
    return round(best * 100)
