"""Embedding contract harnesses: Titan on a stubbed bedrock-runtime client, and the fake."""

import io
import json
from decimal import Decimal
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ReadTimeoutError
from botocore.response import StreamingBody
from botocore.stub import Stubber

from app.adapters.embeddings.bedrock_titan import TitanEmbeddings
from app.adapters.embeddings.fake import FakeEmbeddings
from app.adapters.llm._breaker import BreakerRegistry
from app.adapters.llm._pricing import ModelPrice, PriceTable
from app.adapters.llm._retry import RetryPolicy
from app.adapters.llm.usage_recorder import UsageRecorder
from app.adapters.usage.memory_sink import MemoryUsageSink

MODEL = "amazon.titan-embed-text-v2:0"
DIMS = 512
_DUMMY = {"aws_access_key_id": "AKIDUMMYDUMMYDUMMY00", "aws_secret_access_key": "dummy-secret"}


def titan_prices() -> PriceTable:
    return PriceTable(
        {("bedrock_titan", MODEL): ModelPrice(input_per_m=Decimal("0.02"), output_per_m=Decimal(0))}
    )


def _reply(tokens: int) -> dict[str, Any]:
    vec = [1.0] + [0.0] * (DIMS - 1)
    raw = json.dumps({"embedding": vec, "inputTextTokenCount": tokens}).encode()
    body = StreamingBody(io.BytesIO(raw), len(raw))
    return {"body": body, "contentType": "application/json"}


class TitanHarness:
    name = "bedrock_titan"
    supports_failures = True

    def __init__(self) -> None:
        session = boto3.session.Session(region_name="us-east-1", **_DUMMY)
        self.client = session.client(
            "bedrock-runtime", config=Config(retries={"total_max_attempts": 1})
        )
        self.stubber = Stubber(self.client)
        self.stubber.activate()
        self.sink = MemoryUsageSink()
        self.timeout_next = False
        self._stubbed = self.client.invoke_model
        self.client.invoke_model = self._invoke  # type: ignore[method-assign]

    def _invoke(self, **kwargs: Any) -> Any:
        if self.timeout_next:
            raise ReadTimeoutError(endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com")
        return self._stubbed(**kwargs)

    def provider(self, retry: RetryPolicy) -> TitanEmbeddings:
        return TitanEmbeddings(
            region="us-east-1",
            client=self.client,
            retry=retry,
            breakers=BreakerRegistry(),
            recorder=UsageRecorder(self.sink, titan_prices()),
            prices=titan_prices(),
        )

    def ok(self, tokens: int = 7) -> None:
        self.stubber.add_response("invoke_model", _reply(tokens))

    def throttle(self) -> None:
        self.stubber.add_client_error("invoke_model", "ThrottlingException", "slow", 429)

    def timeout(self) -> None:
        self.timeout_next = True

    def script_ok(self, n: int) -> None:
        for _ in range(n):
            self.ok()


class FakeHarness:
    name = "fake"
    supports_failures = False

    def __init__(self) -> None:
        self.sink = MemoryUsageSink()

    def provider(self, retry: RetryPolicy) -> FakeEmbeddings:
        return FakeEmbeddings(DIMS)

    def script_ok(self, n: int) -> None:
        return None
