"""Remove invisible and bidi-control characters that can hide or reorder text."""

_ALWAYS = frozenset(
    [0x200B, 0x200E, 0x200F, 0xFEFF, 0x00AD]
    + list(range(0x2060, 0x2065))
    + list(range(0x202A, 0x202F))
    + list(range(0x2066, 0x206A))
    + list(range(0xE0000, 0xE0080))
)
_JOINERS = frozenset([0x200C, 0x200D])  # ZWNJ / ZWJ: needed inside Bangla conjuncts


def _bengali(char: str) -> bool:
    return 0x0980 <= ord(char) <= 0x09FF


def strip_invisible(text: str) -> str:
    """Drop the listed invisible characters; keep a joiner only between two Bengali characters."""
    out: list[str] = []
    last = len(text) - 1
    for i, char in enumerate(text):
        code = ord(char)
        if code in _ALWAYS:
            continue
        if code in _JOINERS and not (
            0 < i < last and _bengali(text[i - 1]) and _bengali(text[i + 1])
        ):
            continue
        out.append(char)
    return "".join(out)
