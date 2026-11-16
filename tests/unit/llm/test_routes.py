from pathlib import Path

import pytest
import yaml

from app.adapters.llm._pricing import PriceTable
from app.config.llm_routes import KNOWN_STEPS, RouteTable, load_route_table
from app.config.llm_settings import LlmSettings
from app.config.settings import ConfigError
from app.ports.llm_errors import LLMBadRequest

SONNET = "us.anthropic.claude-sonnet-4-6"
GLOBAL = "global.anthropic.claude-sonnet-4-6"


def _prices() -> PriceTable:
    return PriceTable.from_file(LlmSettings().prices_file)


def _load(**kw: object) -> RouteTable:
    return load_route_table(LlmSettings(**kw), _prices())  # type: ignore[arg-type]


def _yaml(tmp_path: Path, doc: dict) -> Path:
    p = tmp_path / "routes.yaml"
    p.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return p


def _doc() -> dict:
    return {
        "defaults": {
            "provider": "bedrock",
            "model": SONNET,
            "timeout_s": 90,
            "max_retries": 4,
            "structured_mode": "prompt",
        },
        "steps": {s: {"max_tokens": 100, "temperature": 0} for s in sorted(KNOWN_STEPS)},
        "embeddings": {
            "provider": "bedrock_titan",
            "model": "amazon.titan-embed-text-v2:0",
            "dimensions": 512,
            "timeout_s": 20,
        },
    }


def test_shipped_routes_load() -> None:
    t = _load()
    for step in KNOWN_STEPS:
        assert t.resolve(step).step == step
    rw = t.resolve("rewrite")
    assert rw.max_tokens == 8000 and rw.timeout_s == 150 and rw.stream
    fb = t.fallback_for("jd_extract")
    assert fb is not None and fb.model == GLOBAL
    assert t.resolve("jd_extract").max_attempts == 4
    assert t.embeddings.dimensions == 512


def test_structured_mode_per_step() -> None:
    t = _load()
    assert t.resolve("gap_questions").structured_mode == "native"
    for step in KNOWN_STEPS - {"gap_questions"}:
        assert t.resolve(step).structured_mode == "prompt"


def test_unknown_step_in_yaml_fails(tmp_path: Path) -> None:
    d = _doc()
    d["steps"]["bogus_step"] = {"max_tokens": 10, "temperature": 0}
    with pytest.raises(ConfigError, match="bogus_step"):
        _load(routes_file=_yaml(tmp_path, d))


def test_unknown_provider_fails(tmp_path: Path) -> None:
    d = _doc()
    d["steps"]["rewrite"]["provider"] = "nonesuch"
    with pytest.raises(ConfigError, match="nonesuch"):
        _load(routes_file=_yaml(tmp_path, d))


def test_model_without_price_fails_with_clear_message(tmp_path: Path) -> None:
    d = _doc()
    d["steps"]["rewrite"]["model"] = "us.anthropic.unpriced-model"
    with pytest.raises(ConfigError) as ei:
        _load(routes_file=_yaml(tmp_path, d))
    msg = str(ei.value)
    assert "steps.rewrite" in msg
    assert "us.anthropic.unpriced-model" in msg
    assert "llm_prices.yaml" in msg


@pytest.mark.parametrize("bad", [None, 0, -5])
def test_missing_max_tokens_or_nonpositive_fails(tmp_path: Path, bad: int | None) -> None:
    d = _doc()
    if bad is None:
        del d["steps"]["rewrite"]["max_tokens"]
    else:
        d["steps"]["rewrite"]["max_tokens"] = bad
    with pytest.raises(ConfigError, match="max_tokens"):
        _load(routes_file=_yaml(tmp_path, d))


def test_env_default_provider_fake_sets_fake_model_and_no_fallback() -> None:
    t = _load(default_provider="fake")
    r = t.resolve("rewrite")
    assert (r.provider, r.model) == ("fake", "fake-1")
    assert t.fallback_for("rewrite") is None


def test_env_default_provider_openai_without_model_fails() -> None:
    with pytest.raises(ConfigError, match="LLM__DEFAULT_MODEL"):
        _load(default_provider="openai")


def test_env_default_provider_with_model_needs_price(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="llm_prices.yaml"):
        _load(default_provider="openai", default_model="gpt-x")


def test_resolve_unknown_step_raises_bad_request() -> None:
    with pytest.raises(LLMBadRequest):
        _load().resolve("nope")
    assert _load().fallback_for("nope") is None


def test_override_returns_new_table() -> None:
    t = _load()
    t2 = t.override("rewrite", max_tokens=123, timeout_s=5)
    assert t2 is not t
    assert t2.resolve("rewrite").max_tokens == 123
    assert t2.resolve("rewrite").timeout_s == 5
    assert t.resolve("rewrite").max_tokens == 8000
    assert t2.resolve("jd_extract") == t.resolve("jd_extract")


@pytest.mark.parametrize("fb", [{"provider": "bedrock"}, {"model": SONNET}, "oops", ["x"]])
def test_malformed_fallback_fails_with_config_error(tmp_path: Path, fb: object) -> None:
    d = _doc()
    d["defaults"]["fallback"] = fb
    with pytest.raises(ConfigError, match="fallback"):
        _load(routes_file=_yaml(tmp_path, d))


@pytest.mark.parametrize("where", ["defaults", "step"])
@pytest.mark.parametrize("bad", [["a", "b"], "text", 5])
def test_non_mapping_defaults_or_step_fails(tmp_path: Path, where: str, bad: object) -> None:
    d = _doc()
    if where == "defaults":
        d["defaults"] = bad
    else:
        d["steps"]["rewrite"] = bad
    with pytest.raises(ConfigError, match="defaults|steps.rewrite"):
        _load(routes_file=_yaml(tmp_path, d))


def test_non_mapping_embeddings_fails(tmp_path: Path) -> None:
    d = _doc()
    d["embeddings"] = ["x"]
    with pytest.raises(ConfigError, match="embeddings"):
        _load(routes_file=_yaml(tmp_path, d))


def test_env_default_model_only_overrides_model_keeps_fallback(tmp_path: Path) -> None:
    t = _load(default_model=GLOBAL)
    assert t.resolve("rewrite").model == GLOBAL
    assert t.resolve("rewrite").provider == "bedrock"
    assert t.fallback_for("rewrite") is not None
