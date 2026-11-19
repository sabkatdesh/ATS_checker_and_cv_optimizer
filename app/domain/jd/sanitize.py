"""Clean a job description before the model sees it; flag injection markers (spec 10 section 5).

Only invisible characters, markup and data blobs are removed. Nothing is truncated: the input
validator already rejects text over 15k characters.
"""

import re

from pydantic import BaseModel

from app.domain.jd.markers import MARKER_CODES, MarkerCode, find_markers
from app.domain.text.invisible import strip_invisible

_SCRIPT_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_BLOCK_END = re.compile(r"<\s*(?:br\s*/?|/p|/div|/li|/h[1-6]|/tr)\s*>", re.IGNORECASE)
_TAG = re.compile(r"</?[A-Za-z][^<>]*>")
_DATA_URI = re.compile(r"data:[\w.+/-]*(?:;[\w=.+-]+)*;base64,[A-Za-z0-9+/=]+", re.IGNORECASE)
_SPACES = re.compile(r"[^\S\n]+")
_BLANK_LINES = re.compile(r"\n{3,}")


class SanitizedJD(BaseModel, frozen=True):
    text: str
    markers: tuple[MarkerCode, ...] = ()


def _clean(text: str) -> str:
    text = _SCRIPT_STYLE.sub("", text)
    text = _COMMENT.sub("", text)
    text = _BLOCK_END.sub("\n", text)
    text = _TAG.sub("", text)
    text = _DATA_URI.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = (_SPACES.sub(" ", line).strip() for line in text.split("\n"))
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def sanitize_jd(text: str) -> SanitizedJD:
    visible = strip_invisible(text)
    clean = _clean(visible)
    # Tag markers are looked for before the tags are stripped.
    found = set(find_markers(visible)) | set(find_markers(clean))
    return SanitizedJD(text=clean, markers=tuple(c for c in MARKER_CODES if c in found))
