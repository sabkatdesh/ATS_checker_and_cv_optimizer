"""One JSON POST over httpx with provider errors mapped to LLMError.

A new AsyncClient is built per call so no connection pool is tied to a closed event loop.
Error `detail` is "HTTP <status>" only: response bodies can echo request content.
"""

from typing import Any

import httpx

from app.ports.llm_errors import (
    LLMAuthError,
    LLMBadRequest,
    LLMError,
    LLMThrottled,
    LLMTimeout,
    LLMUnavailable,
)


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        seconds = float(raw.strip())
    except ValueError:  # an HTTP-date: the retry layer's own backoff applies
        return None
    return seconds if 0 <= seconds < float("inf") else None


def status_error(response: httpx.Response, *, provider: str, model: str) -> LLMError:
    status = response.status_code
    detail = f"HTTP {status}"
    if status == 429:
        return LLMThrottled(
            detail, provider=provider, model=model, retry_after_s=_retry_after(response)
        )
    if status in (401, 403):
        return LLMAuthError(detail, provider=provider, model=model)
    if status >= 500:
        return LLMUnavailable(detail, provider=provider, model=model)
    return LLMBadRequest(detail, provider=provider, model=model)


async def post_json(
    url: str,
    *,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout_s: float,
    provider: str,
    model: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(transport=transport, timeout=timeout_s) as client:
            response = await client.post(url, headers=headers, json=body)
    except httpx.TimeoutException:
        raise LLMTimeout("timeout", provider=provider, model=model) from None
    except httpx.HTTPError:
        raise LLMUnavailable("transport error", provider=provider, model=model) from None
    if response.status_code >= 400:
        raise status_error(response, provider=provider, model=model)
    try:
        data = response.json()
    except ValueError:
        raise LLMUnavailable("invalid response body", provider=provider, model=model) from None
    if not isinstance(data, dict):
        raise LLMUnavailable("invalid response body", provider=provider, model=model)
    return data
