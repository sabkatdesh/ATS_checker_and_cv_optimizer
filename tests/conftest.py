"""
Shared fixtures for all tests.
"""
import json
import os
from pathlib import Path

import pytest

TEST_SET_DIR = Path(__file__).parent.parent / "data" / "test_set"


def load_test_pair(name: str) -> dict:
    """Load a CV+JD test pair from data/test_set/{name}.json"""
    path = TEST_SET_DIR / f"{name}.json"
    if not path.exists():
        pytest.skip(f"Test data file not found: {path}")
    with open(path) as f:
        return json.load(f)


@pytest.fixture
def tech_junior():
    return load_test_pair("tech_junior")

@pytest.fixture
def tech_senior():
    return load_test_pair("tech_senior")

@pytest.fixture
def medical_nurse():
    return load_test_pair("medical_nurse")

@pytest.fixture
def education_teacher():
    return load_test_pair("education_teacher")

@pytest.fixture
def trades_electrician():
    return load_test_pair("trades_electrician")

@pytest.fixture
def finance_analyst():
    return load_test_pair("finance_analyst")


ALL_TEST_PAIRS = [
    "tech_junior", "tech_senior", "tech_fresher", "tech_poor_format",
    "medical_nurse", "education_teacher", "trades_electrician", "finance_analyst",
]
