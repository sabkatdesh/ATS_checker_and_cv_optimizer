"""LLM settings nested under AppSettings.llm (env prefix LLM__)."""

from pathlib import Path

from pydantic import BaseModel, SecretStr

_CONFIG_DIR = Path(__file__).resolve().parent


class LlmSettings(BaseModel):
    routes_file: Path = _CONFIG_DIR / "llm_routes.yaml"
    prices_file: Path = _CONFIG_DIR / "llm_prices.yaml"
    default_provider: str | None = None
    default_model: str | None = None
    aws_region: str = "us-east-1"
    bedrock_read_timeout_s: float = 160
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    gemini_api_key: SecretStr | None = None
    ollama_base_url: str = "http://localhost:11434"
