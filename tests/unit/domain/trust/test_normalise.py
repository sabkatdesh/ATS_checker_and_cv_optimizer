from decimal import Decimal

import pytest

from app.domain.trust.aliases import SKILL_ALIASES, canonical_skill
from app.domain.trust.normalise import normalise_text, parse_numbers


def test_normalise_casefolds_strips_markup_and_maps_bangla_digits():
    assert normalise_text("# `Dhaka`  Medical, College!") == "dhaka medical college"
    assert normalise_text("৩০% ২০২১") == "30 2021"


def test_normalise_keeps_bangla_vowel_signs():
    assert normalise_text("ঢাকা মেডিকেল কলেজ") == "ঢাকা মেডিকেল কলেজ"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Cut time by 40%", ["40"]),
        ("Cut time by ৪০%", ["40"]),
        ("Raised BDT 1,200 and Tk 12 000 and ৳500", ["1200", "12000", "500"]),
        ("Tk5000 budget, $3.5M fund, 20k users", ["5000", "3500000", "20000"]),
        ("Since 2019, led 2019-2021 work; Jan 2020 to present", []),
        ("Served 2000 patients", ["2000"]),
        ("Promoted 05/2019; EC2, Python3, 3D, 1st, v2.1, 24/7 support", []),
    ],
)
def test_parse_numbers(text: str, expected: list[str]):
    assert parse_numbers(text) == [Decimal(v) for v in expected]


def test_skill_aliases():
    assert len(SKILL_ALIASES) >= 40
    assert canonical_skill("JS") == canonical_skill("JavaScript") == "javascript"
    assert canonical_skill("k8s") == "kubernetes"
    assert canonical_skill("MS Excel") == "excel"
    assert canonical_skill("Postgres") == canonical_skill("PostgreSQL")
    assert canonical_skill("Node.js") == canonical_skill("nodejs")
