from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.llm._pricing import PriceTable
from app.config.llm_settings import LlmSettings
from app.config.settings import AppSettings, ConfigError
from app.ports.llm import Usage

SONNET = "us.anthropic.claude-sonnet-4-6"


@pytest.fixture
def prices() -> PriceTable:
    return PriceTable.from_file(LlmSettings().prices_file)


def test_cost_matches_table(prices: PriceTable) -> None:
    cost = prices.cost(
        "bedrock", SONNET, Usage(input_tokens=1000, output_tokens=500, cache_read_tokens=2000)
    )
    assert cost == Decimal("0.003000") + Decimal("0.007500") + Decimal("0.000600")
    assert cost == Decimal("0.011100")


def test_cost_quantised_to_6dp(prices: PriceTable) -> None:
    cost = prices.cost("bedrock_titan", "amazon.titan-embed-text-v2:0", Usage(input_tokens=1))
    assert cost == Decimal("0.000000")
    assert cost.as_tuple().exponent == -6
    half_up = prices.cost("bedrock", SONNET, Usage(cache_read_tokens=5))  # 0.0000015 -> 0.000002
    assert half_up == Decimal("0.000002")


def test_has_and_unknown_price(prices: PriceTable) -> None:
    assert prices.has("fake", "fake-1")
    assert not prices.has("bedrock", "nope")
    with pytest.raises(KeyError):
        prices.price_for("bedrock", "nope")


def test_fake_is_free(prices: PriceTable) -> None:
    assert prices.cost(
        "fake", "fake-1", Usage(input_tokens=10**6, output_tokens=10**6, cache_read_tokens=10**6)
    ) == Decimal("0")


def test_malformed_price_file_raises_config_error(tmp_path: Path) -> None:
    bad = tmp_path / "p.yaml"
    bad.write_text("bedrock:\n  m: {input_per_m: 1}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="llm_prices|p.yaml"):
        PriceTable.from_file(bad)


def test_settings_llm_nested_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM__DEFAULT_PROVIDER", "fake")
    monkeypatch.setenv("LLM__AWS_REGION", "eu-west-1")
    s = AppSettings(_env_file=None)
    assert s.llm.default_provider == "fake"
    assert s.llm.aws_region == "eu-west-1"
    assert s.llm.routes_file.name == "llm_routes.yaml"
