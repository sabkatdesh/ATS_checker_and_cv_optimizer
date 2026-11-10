"""Shim kept until Task 10: core/pipeline/nodes.py still builds its LLM at import time.

Configuration now comes from AppSettings (which reads .env itself), not os.environ.
"""

from typing import Any

from app.adapters.llm.azure_legacy import AzureLLMClient, build_azure_client
from app.config.settings import load_settings

__all__ = ["AzureLLMClient", "get_llm"]

_client: AzureLLMClient | None = None


def get_llm() -> Any:
    """Return the shared LangChain model (created on first call)."""
    global _client
    if _client is None:
        _client = build_azure_client(load_settings())
    return _client.llm
