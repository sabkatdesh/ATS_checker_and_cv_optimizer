"""Match protected CV entries between a source CV and a rewrite, tolerating small rewordings."""

import re
from collections.abc import Callable, Sequence
from difflib import SequenceMatcher
from typing import Any

MATCH_RATIO = 0.9


def _norm(*values: Any) -> str:
    text = " ".join(str(v or "") for v in values).lower()
    return " ".join(re.sub(r"[^\w\s]", "", text).split())


ENTRY_KEY: dict[str, Callable[[Any], str]] = {
    "education": lambda e: _norm(e.degree, e.institution),
    "licenses": lambda e: _norm(e.name),
    "certifications": lambda e: _norm(e.name),
    "clinical_practice": lambda e: _norm(e.setting, e.institution),
    "trade_qualifications": lambda e: _norm(e.qualification),
}


def unmatched_source_entries(
    section: str, source: Sequence[Any], output: Sequence[Any]
) -> list[Any]:
    """Source entries with no output counterpart; each output entry matches at most one source.

    Exact keys pair first, so "NC-3" and "NC-2" never consume each other's match; the rest
    pair by descending similarity while the ratio is at least MATCH_RATIO.
    """
    key = ENTRY_KEY[section]
    src_keys = [key(e) for e in source]
    free = [key(e) for e in output]
    open_src: list[int] = []
    for i, k in enumerate(src_keys):
        if k in free:
            free.remove(k)
        else:
            open_src.append(i)
    pairs = sorted(
        (
            (SequenceMatcher(None, src_keys[i], k).ratio(), i, j)
            for i in open_src
            for j, k in enumerate(free)
        ),
        reverse=True,
    )
    used_src: set[int] = set()
    used_out: set[int] = set()
    for ratio, i, j in pairs:
        if ratio < MATCH_RATIO:
            break
        if i not in used_src and j not in used_out:
            used_src.add(i)
            used_out.add(j)
    return [source[i] for i in open_src if i not in used_src]
