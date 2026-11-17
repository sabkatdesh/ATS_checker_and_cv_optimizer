from app.domain.trust.fuzzy import token_set_ratio


def test_subset_names_match():
    assert token_set_ratio("Dhaka Medical College", "dhaka medical college hospital") >= 90


def test_different_employers_do_not_match():
    assert token_set_ratio("Google", "Grameenphone") < 90


def test_identical_and_empty():
    assert token_set_ratio("Example Bank PLC", "example bank plc") == 100
    assert token_set_ratio("", "Example") == 0
