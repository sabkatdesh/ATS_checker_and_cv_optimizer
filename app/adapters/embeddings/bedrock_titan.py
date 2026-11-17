"""Amazon Titan Text Embeddings V2 on Bedrock (one invoke_model per text).

Titan V2 has no input-type switch, so `purpose` ("document" or "query") is accepted for the
port and does not change the request. Errors carry error codes only, never input text.
"""

import asyncio
import json
import threading
import time
from typing import Any

import boto3
from botocore.config import Config

from app.adapters.llm._bedrock_wire import TRANSPORT_ERRORS, map_error
from app.adapters.llm._breaker import BreakerRegistry
from app.adapters.llm._pricing import PriceTable
from app.adapters.llm._retry import Deadline, RetryPolicy, call_with_retry
from app.adapters.llm.bedrock_converse import (
    CONNECT_TIMEOUT_S,
    MAX_POOL_CONNECTIONS,
    in_daemon_thread,
)
from app.adapters.llm.usage_recorder import UsageRecorder
from app.ports.embeddings import Purpose
from app.ports.llm import CancelToken, Usage
from app.ports.llm_errors import LLMBadRequest, LLMError, LLMTimeout, LLMUnavailable

PROVIDER = "bedrock_titan"
MAX_CHARS = 50_000
CONCURRENCY = 4


class TitanEmbeddings:
    name = PROVIDER

    def __init__(
        self,
        *,
        region: str,
        retry: RetryPolicy,
        breakers: BreakerRegistry,
        recorder: UsageRecorder | None,
        prices: PriceTable,
        model: str = "amazon.titan-embed-text-v2:0",
        dimensions: int = 512,
        timeout_s: float = 20,
        client: Any | None = None,
    ) -> None:
        self._region = region
        self._model = model
        self.dimensions = dimensions
        self._timeout_s = timeout_s
        self._client = client
        self._retry = retry
        self._breakers = breakers
        self._recorder = recorder
        self._prices = prices
        self._lock = threading.Lock()

    def _get_client(self) -> Any:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    config = Config(
                        connect_timeout=CONNECT_TIMEOUT_S,
                        read_timeout=self._timeout_s,
                        max_pool_connections=MAX_POOL_CONNECTIONS,
                        retries={"mode": "adaptive", "total_max_attempts": 1},
                    )
                    self._client = boto3.session.Session().client(
                        "bedrock-runtime", region_name=self._region, config=config
                    )
        return self._client

    def _invoke(self, text: str) -> tuple[list[float], int]:
        body = json.dumps({"inputText": text, "dimensions": self.dimensions, "normalize": True})
        try:
            resp = self._get_client().invoke_model(
                modelId=self._model,
                body=body,
                accept="application/json",
                contentType="application/json",
            )
            data = json.loads(resp["body"].read())
            vec = [float(x) for x in data["embedding"]]
            tokens = int(data.get("inputTextTokenCount", 0))
        except TRANSPORT_ERRORS as exc:
            raise map_error(exc, model=self._model) from None
        except (ValueError, KeyError, TypeError):  # malformed reply; never echo it
            raise LLMUnavailable(
                "malformed embedding reply", provider=PROVIDER, model=self._model
            ) from None
        if len(vec) != self.dimensions:
            raise LLMUnavailable("wrong embedding size", provider=PROVIDER, model=self._model)
        return vec, tokens

    async def _attempt(self, text: str, timeout_s: float) -> tuple[list[float], int]:
        breaker = self._breakers.get(PROVIDER, self._model)
        generation = breaker.before_call()
        outcome = "release"
        try:
            result = await asyncio.wait_for(in_daemon_thread(lambda: self._invoke(text)), timeout_s)
            outcome = "success"
            return result
        except TimeoutError:
            outcome = "failure"
            raise LLMTimeout("deadline exceeded", provider=PROVIDER, model=self._model) from None
        except LLMError as err:
            if err.trips_breaker:
                outcome = "failure"
            raise
        finally:
            if outcome == "success":
                breaker.record_success(generation)
            elif outcome == "failure":
                breaker.record_failure(generation)
            else:  # cancelled or caller error: free a half-open probe
                breaker.release_probe(generation)

    async def _one(
        self, text: str, sem: asyncio.Semaphore, cancel: CancelToken
    ) -> tuple[list[float], int, int]:
        async with sem:
            deadline = Deadline(self._timeout_s)  # starts when this text's request starts
            tried = 0

            async def attempt(timeout_s: float) -> tuple[list[float], int]:
                nonlocal tried
                tried += 1
                return await self._attempt(text, timeout_s)

            try:
                (vec, tokens), attempts = await call_with_retry(
                    attempt,
                    policy=self._retry,
                    deadline=deadline,
                    cancel=cancel,
                    on_failure=lambda _err: None,
                )
            except LLMError as err:
                err.attempts = tried
                raise
        return vec, tokens, attempts

    def _validate(self, texts: list[str]) -> None:
        for t in texts:
            if not t.strip():
                raise LLMBadRequest("empty text", provider=PROVIDER, model=self._model)
            if len(t) > MAX_CHARS:
                raise LLMBadRequest("text too long", provider=PROVIDER, model=self._model)

    async def embed(self, texts: list[str], purpose: Purpose) -> list[list[float]]:
        """One call per text, up to CONCURRENCY at once, results in input order."""
        self._validate(texts)
        if not texts:
            return []
        start = time.monotonic()
        cancel = CancelToken()
        sem = asyncio.Semaphore(CONCURRENCY)
        tasks = [asyncio.ensure_future(self._one(t, sem, cancel)) for t in texts]
        try:
            done = await asyncio.gather(*tasks)
        except BaseException as exc:
            cancel.cancel()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if isinstance(exc, LLMError):
                self._record(Usage(), start, exc.attempts or 1, exc)
            raise
        tokens = sum(d[1] for d in done)
        self._record(Usage(input_tokens=tokens), start, max((d[2] for d in done), default=1), None)
        return [d[0] for d in done]

    def _record(self, usage: Usage, start: float, attempts: int, err: LLMError | None) -> None:
        if self._recorder is None:
            return
        self._recorder.record_embedding(
            provider=PROVIDER,
            model=self._model,
            usage=usage,
            latency_ms=int((time.monotonic() - start) * 1000),
            attempts=attempts,
            error=err,
        )
