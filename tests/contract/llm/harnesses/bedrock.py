"""Bedrock contract harness: botocore Stubber on a real bedrock-runtime client.

The client is built with static dummy credentials (never env or profile), and the Stubber
answers every call, so no request leaves the process. Hang and Timeout cannot be expressed
as stubbed responses, so the client's converse method is wrapped to sleep or raise for them.
"""

import json
import time
from collections import deque
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ReadTimeoutError
from botocore.stub import Stubber

from app.adapters.llm._base import BaseProvider
from app.adapters.llm._breaker import BreakerRegistry
from app.adapters.llm._pricing import PriceTable
from app.adapters.llm._retry import RetryPolicy
from app.adapters.llm.bedrock_converse import BedrockConverseTransport
from tests.contract.llm import harness as h

_DUMMY = {"aws_access_key_id": "AKIDUMMYDUMMYDUMMY00", "aws_secret_access_key": "dummy-secret"}


def _body(text: str, stop: str, in_tok: int = 10, out_tok: int = 5) -> dict:
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "stopReason": stop,
        "usage": {"inputTokens": in_tok, "outputTokens": out_tok, "totalTokens": in_tok + out_tok},
        "metrics": {"latencyMs": 1},
    }


class BedrockHarness:
    name = "bedrock"
    supports_native = True

    def __init__(self) -> None:
        session = boto3.session.Session(region_name="us-east-1", **_DUMMY)
        self.client = session.client(
            "bedrock-runtime", config=Config(retries={"total_max_attempts": 1})
        )
        self.stubber = Stubber(self.client)
        self.stubber.activate()
        self._stubbed = self.client.converse
        self._special: deque[h.Outcome | None] = deque()
        self._sent: list[dict[str, Any]] = []
        self.client.converse = self._converse  # type: ignore[method-assign]

    def _converse(self, **kwargs: Any) -> dict:
        self._sent.append(kwargs)
        special = self._special.popleft() if self._special else None
        if isinstance(special, h.Hang):
            time.sleep(special.seconds)
            return _body("{}", "end_turn")
        if isinstance(special, h.Timeout):
            raise ReadTimeoutError(endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com")
        return self._stubbed(**kwargs)

    def provider(self, prices: PriceTable, breakers: BreakerRegistry, retry: RetryPolicy):
        transport = BedrockConverseTransport(
            region="us-east-1", read_timeout_s=10, client=self.client
        )
        return BaseProvider(transport, prices=prices, breakers=breakers, retry=retry)

    def script(self, *outcomes: h.Outcome) -> None:
        for o in outcomes:
            self._special.append(o if isinstance(o, h.Hang | h.Timeout) else None)
            match o:
                case h.Ok(text, usage):
                    resp = _body(text, "end_turn", usage.input_tokens, usage.output_tokens)
                    self.stubber.add_response("converse", resp)
                case h.Throttle():
                    self.stubber.add_client_error(
                        "converse", "ThrottlingException", "slow down", 429
                    )
                case h.ServerError():
                    self.stubber.add_client_error(
                        "converse", "ServiceUnavailableException", "unavailable", 500
                    )
                case h.BadRequest():
                    self.stubber.add_client_error(
                        "converse", "ValidationException", "bad input", 400
                    )
                case h.Refusal():
                    self.stubber.add_response("converse", _body("", "content_filtered", 10, 0))
                case h.Empty():
                    self.stubber.add_response("converse", _body("", "end_turn"))
                case h.Truncated(text):
                    self.stubber.add_response("converse", _body(text, "max_tokens"))
                case h.Hang() | h.Timeout():
                    pass
                case _:
                    raise AssertionError(f"unknown outcome {o!r}")

    def sent_bodies(self) -> list[dict]:
        bodies = []
        for kw in self._sent:
            schema = kw.get("outputConfig", {}).get("textFormat", {}).get("structure", {})
            raw_schema = schema.get("jsonSchema", {}).get("schema")
            bodies.append(
                {
                    "model": kw["modelId"],
                    "system": "".join(b.get("text", "") for b in kw.get("system", [])),
                    "max_tokens": kw["inferenceConfig"]["maxTokens"],
                    "messages": [
                        {"role": m["role"], "content": "".join(c["text"] for c in m["content"])}
                        for m in kw["messages"]
                    ],
                    "json_schema": json.loads(raw_schema) if raw_schema else None,
                    "raw": kw,
                }
            )
        return bodies

    def last_roles(self) -> list[str]:
        return [m["role"] for m in self.sent_bodies()[-1]["messages"]]
