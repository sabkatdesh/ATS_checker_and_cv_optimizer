"""Route table loaded from llm_routes.yaml with boot-time validation."""

from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from app.adapters.llm._pricing import PriceTable
from app.config.llm_settings import LlmSettings
from app.config.settings import ConfigError
from app.ports.llm import Route
from app.ports.llm_errors import LLMBadRequest

KNOWN_STEPS = frozenset(
    {
        "jd_extract",
        "cv_extract",
        "eligibility",
        "gap_questions",
        "rewrite",
        "verify_claims",
        "cover_letter",
        "profile_import",
    }
)
KNOWN_PROVIDERS = frozenset(
    {"bedrock", "anthropic", "azure_openai", "openai", "gemini", "ollama", "fake"}
)
_EMBED_PROVIDERS = frozenset({"bedrock_titan", "fake"})


class EmbeddingRoute(BaseModel, frozen=True):
    provider: str
    model: str
    dimensions: int
    timeout_s: float


class RouteTable:
    def __init__(
        self,
        routes: dict[str, Route],
        fallbacks: dict[str, Route | None],
        embeddings: EmbeddingRoute,
    ) -> None:
        self._routes = routes
        self._fallbacks = fallbacks
        self.embeddings = embeddings

    def resolve(self, step: str) -> Route:
        try:
            return self._routes[step]
        except KeyError:
            raise LLMBadRequest(f"unknown step {step!r}") from None

    def fallback_for(self, step: str) -> Route | None:
        return self._fallbacks.get(step)

    def override(self, step: str, **fields: Any) -> "RouteTable":
        new = self.resolve(step).model_copy(update=fields)
        return RouteTable({**self._routes, step: new}, self._fallbacks, self.embeddings)


def _read_yaml(llm: LlmSettings) -> dict[str, Any]:
    try:
        doc = yaml.safe_load(llm.routes_file.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        raise ConfigError(f"Cannot read route file {llm.routes_file.name}") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("steps"), dict):
        raise ConfigError(f"{llm.routes_file.name}: expected 'defaults', 'steps', 'embeddings'")
    return doc


def _apply_env(defaults: dict[str, Any], llm: LlmSettings) -> dict[str, Any]:
    """fake -> fake-1, no fallback. The file's own provider is a no-op (LLM__DEFAULT_MODEL may
    still replace the model). Any other provider needs LLM__DEFAULT_MODEL and drops the fallback.
    """
    d = dict(defaults)
    provider = llm.default_provider
    if provider == "fake":
        d.update(provider="fake", model="fake-1", fallback=None)
    elif provider and provider != d.get("provider"):
        if not llm.default_model:
            raise ConfigError(
                f"LLM__DEFAULT_PROVIDER={provider!r} differs from the routes file provider "
                f"{d.get('provider')!r} and requires LLM__DEFAULT_MODEL"
            )
        d.update(provider=provider, model=llm.default_model, fallback=None)
    elif llm.default_model:
        d["model"] = llm.default_model
    return d


def _check(provider: str, model: str, where: str, prices: PriceTable) -> None:
    if provider not in KNOWN_PROVIDERS:
        raise ConfigError(f"{where}: unknown provider {provider!r}")
    if not prices.has(provider, model):
        raise ConfigError(f"{where}: no price for {provider}/{model}; add it to llm_prices.yaml")


def _build(
    step: str, spec: dict[str, Any], d: dict[str, Any], prices: PriceTable
) -> tuple[Route, Route | None]:
    where = f"steps.{step}"
    merged = {**d, **spec}
    try:
        route = Route(
            step=step,
            provider=merged["provider"],
            model=merged["model"],
            max_tokens=spec.get("max_tokens"),  # type: ignore[arg-type]
            temperature=merged.get("temperature"),
            timeout_s=merged["timeout_s"],
            max_attempts=merged.get("max_retries", 4),
            structured_mode=merged["structured_mode"],
            stream=bool(merged.get("stream", False)),
        )
    except ValidationError as exc:
        bad = ", ".join(".".join(str(p) for p in e["loc"]) for e in exc.errors())
        raise ConfigError(f"{where}: invalid or missing field(s): {bad}") from None
    except KeyError as exc:
        raise ConfigError(f"{where}: missing field {exc.args[0]}") from None
    _check(route.provider, route.model, where, prices)
    fb_spec = merged.get("fallback")
    fb = None
    if fb_spec:
        fb_where = f"{where}.fallback"
        if not isinstance(fb_spec, dict):
            raise ConfigError(f"{fb_where}: must be a mapping with provider and model")
        for key in ("provider", "model"):
            if not isinstance(fb_spec.get(key), str):
                raise ConfigError(f"{fb_where}.{key}: missing or not a string")
        # A fallback inherits the primary's structured_mode, timeouts, tokens and stream.
        fb = route.model_copy(update={"provider": fb_spec["provider"], "model": fb_spec["model"]})
        _check(fb.provider, fb.model, f"{where}.fallback", prices)
    return route, fb


def load_route_table(llm: LlmSettings, prices: PriceTable) -> RouteTable:
    doc = _read_yaml(llm)
    steps: dict[str, Any] = doc["steps"]
    for name in steps:
        if name not in KNOWN_STEPS:
            raise ConfigError(f"steps.{name}: unknown step")
    missing = KNOWN_STEPS - steps.keys()
    if missing:
        raise ConfigError(f"steps: missing {', '.join(sorted(missing))}")
    defaults = doc.get("defaults")
    if defaults is None:
        defaults = {}
    if not isinstance(defaults, dict):
        raise ConfigError("defaults: must be a mapping")
    d = _apply_env(defaults, llm)
    routes: dict[str, Route] = {}
    fallbacks: dict[str, Route | None] = {}
    for name, spec in steps.items():
        if spec is not None and not isinstance(spec, dict):
            raise ConfigError(f"steps.{name}: must be a mapping")
        routes[name], fallbacks[name] = _build(name, spec or {}, d, prices)
    try:
        emb = EmbeddingRoute(**doc["embeddings"])
    except (ValidationError, KeyError, TypeError):  # TypeError: not a mapping
        raise ConfigError("embeddings: invalid or missing") from None
    if emb.provider not in _EMBED_PROVIDERS:
        raise ConfigError(f"embeddings: unknown provider {emb.provider!r}")
    if not prices.has(emb.provider, emb.model):
        raise ConfigError(
            f"embeddings: no price for {emb.provider}/{emb.model}; see llm_prices.yaml"
        )
    return RouteTable(routes, fallbacks, emb)
