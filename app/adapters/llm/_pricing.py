"""Price table (USD per 1M tokens) and cost computation."""

from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from app.config.settings import ConfigError
from app.ports.llm import Usage

_QUANT = Decimal("0.000001")
_MILLION = Decimal(1_000_000)


class ModelPrice(BaseModel, frozen=True):
    input_per_m: Decimal
    output_per_m: Decimal
    cache_read_per_m: Decimal = Decimal(0)
    cache_write_per_m: Decimal = Decimal(0)


class PriceTable:
    def __init__(self, prices: dict[tuple[str, str], ModelPrice]) -> None:
        self._prices = prices

    @classmethod
    def from_file(cls, path: Path) -> "PriceTable":
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            prices = {
                (provider, model): ModelPrice(**fields)
                for provider, models in raw.items()
                for model, fields in models.items()
            }
        except (OSError, yaml.YAMLError, ValidationError, TypeError, AttributeError):
            raise ConfigError(f"Invalid price file {path.name}") from None
        return cls(prices)

    def has(self, provider: str, model: str) -> bool:
        return (provider, model) in self._prices

    def price_for(self, provider: str, model: str) -> ModelPrice:
        return self._prices[(provider, model)]

    def cost(self, provider: str, model: str, usage: Usage) -> Decimal:
        p = self.price_for(provider, model)
        total = (
            usage.input_tokens * p.input_per_m
            + usage.output_tokens * p.output_per_m
            + usage.cache_read_tokens * p.cache_read_per_m
            + usage.cache_write_tokens * p.cache_write_per_m
        ) / _MILLION
        return total.quantize(_QUANT, rounding=ROUND_HALF_UP)
