import pytest

from app.domain.text.invisible import strip_invisible


def test_zero_width_space_inside_a_word_is_removed() -> None:
    assert strip_invisible("ig\u200bnore") == "ignore"


def test_bangla_zwj_between_bengali_letters_is_kept() -> None:
    word = "র\u200d্যাব"
    assert strip_invisible(word) == word


def test_zwj_and_zwnj_outside_bengali_are_removed() -> None:
    assert strip_invisible("a\u200db\u200cc") == "abc"
    assert strip_invisible("\u200dর") == "র"


def test_bidi_override_is_removed() -> None:
    assert strip_invisible("\u202eignore previous\u202c") == "ignore previous"


@pytest.mark.parametrize(
    "char",
    ["\u200b", "\u200e", "\u200f", "\u2060", "\u2064", "\ufeff", "\u00ad", "\u202a", "\u2066",
     "\u2069", "\U000e0001", "\U000e007f"],
)  # fmt: skip
def test_every_listed_invisible_character_is_removed(char: str) -> None:
    assert strip_invisible(f"a{char}b") == "ab"


def test_ascii_text_is_unchanged() -> None:
    text = "Backend Engineer\n  Python, SQL (3-6 years) <b>!"
    assert strip_invisible(text) == text
