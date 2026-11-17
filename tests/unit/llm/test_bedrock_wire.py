"""Bedrock Converse wire format: request kwargs, response parsing, stream accumulation, errors."""

import json

import pytest
from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    CredentialRetrievalError,
    EndpointConnectionError,
    EventStreamError,
    HTTPClientError,
    NoCredentialsError,
    NoRegionError,
    PartialCredentialsError,
    ProxyConnectionError,
    ReadTimeoutError,
    ResponseStreamingError,
    SSLError,
    TokenRetrievalError,
)
from botocore.exceptions import ConnectionError as BotoConnectionError
from urllib3.exceptions import ProtocolError
from urllib3.exceptions import ReadTimeoutError as Urllib3ReadTimeout

from app.adapters.llm._base import WireRequest
from app.adapters.llm._bedrock_wire import (
    accumulate_stream,
    build_converse_kwargs,
    estimate_tokens,
    map_error,
    parse_converse,
)
from app.ports.llm import CancelToken, Message, Usage
from app.ports.llm_errors import (
    LLMAuthError,
    LLMBadRequest,
    LLMCancelled,
    LLMThrottled,
    LLMTimeout,
    LLMUnavailable,
)

MODEL = "us.anthropic.claude-sonnet-4-6"
SECRET = "SENTINEL-AWS-MESSAGE-91c2"


def wire(**over) -> WireRequest:
    base = dict(
        system="be brief",
        messages=(Message(role="user", content="hello"),),
        model=MODEL,
        max_tokens=321,
        temperature=0.0,
        json_schema=None,
        schema_name=None,
        cache_prefix=False,
        stream=False,
        timeout_s=30.0,
    )
    base.update(over)
    return WireRequest(**base)  # type: ignore[arg-type]


def client_error(code: str, status: int, message: str = SECRET) -> ClientError:
    body = {
        "Error": {"Code": code, "Message": message},
        "ResponseMetadata": {"HTTPStatusCode": status},
    }
    return ClientError(body, "Converse")  # type: ignore[arg-type]


def response(stop: str = "end_turn", text: str = "hi") -> dict:
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "stopReason": stop,
        "usage": {
            "inputTokens": 12,
            "outputTokens": 3,
            "totalTokens": 15,
            "cacheReadInputTokens": 4,
            "cacheWriteInputTokens": 2,
        },
        "metrics": {"latencyMs": 9},
    }


def test_kwargs_always_have_max_tokens():
    kw = build_converse_kwargs(wire(temperature=None))
    assert kw["modelId"] == MODEL
    assert kw["inferenceConfig"] == {"maxTokens": 321}
    assert kw["messages"] == [{"role": "user", "content": [{"text": "hello"}]}]
    assert build_converse_kwargs(wire())["inferenceConfig"] == {"maxTokens": 321, "temperature": 0}
    assert "outputConfig" not in kw


def test_no_system_block_when_empty():
    assert "system" not in build_converse_kwargs(wire(system=""))
    assert build_converse_kwargs(wire())["system"] == [{"text": "be brief"}]


def test_cache_point_only_when_prefix_ge_2048_tokens():
    long = "x" * (2048 * 4)
    short = "x" * (2048 * 4 - 4)
    assert estimate_tokens(long) == 2048 and estimate_tokens(short) == 2047
    cached = build_converse_kwargs(wire(system=long, cache_prefix=True))["system"]
    assert cached == [{"text": long}, {"cachePoint": {"type": "default"}}]
    assert len(build_converse_kwargs(wire(system=short, cache_prefix=True))["system"]) == 1
    assert len(build_converse_kwargs(wire(system=long, cache_prefix=False))["system"]) == 1


def test_output_config_shape_matches_spike():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
    kw = build_converse_kwargs(wire(json_schema=schema, schema_name="Answer"))
    fmt = kw["outputConfig"]["textFormat"]
    assert set(kw["outputConfig"]) == {"textFormat"}
    assert fmt["type"] == "json_schema"
    js = fmt["structure"]["jsonSchema"]
    assert set(fmt["structure"]) == {"jsonSchema"}
    assert set(js) == {"schema", "name", "description"}
    assert json.loads(js["schema"]) == schema and js["name"] == "Answer"


@pytest.mark.parametrize(
    ("raw", "stop"),
    [
        ("end_turn", "end"),
        ("stop_sequence", "end"),
        ("max_tokens", "max_tokens"),
        ("content_filtered", "refused"),
        ("guardrail_intervened", "refused"),
        ("tool_use", "other"),
    ],
)
def test_parse_stop_reasons(raw, stop):
    got = parse_converse(response(raw))
    assert got.stop == stop and got.raw_stop_reason == raw and got.text == "hi"
    assert got.usage == Usage(
        input_tokens=12, output_tokens=3, cache_read_tokens=4, cache_write_tokens=2
    )


def test_parse_joins_text_blocks_and_skips_others():
    resp = response()
    resp["output"]["message"]["content"] = [{"text": "a"}, {"reasoningContent": {}}, {"text": "b"}]
    assert parse_converse(resp).text == "ab"


def _events() -> list[dict]:
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockDelta": {"delta": {"text": "Hel"}, "contentBlockIndex": 0}},
        {"contentBlockDelta": {"delta": {"text": "lo"}, "contentBlockIndex": 0}},
        {"contentBlockStop": {"contentBlockIndex": 0}},
        {"messageStop": {"stopReason": "max_tokens"}},
        {"metadata": {"usage": {"inputTokens": 7, "outputTokens": 2, "totalTokens": 9}}},
    ]


def test_stream_accumulates_text_and_usage():
    got = accumulate_stream(_events(), CancelToken())
    assert got.text == "Hello" and got.stop == "max_tokens"
    assert got.usage == Usage(input_tokens=7, output_tokens=2)


def test_stream_stops_on_cancel():
    cancel = CancelToken()
    seen: list[dict] = []

    def events():
        for i, ev in enumerate(_events()):
            seen.append(ev)
            if i == 1:
                cancel.cancel()
            yield ev

    with pytest.raises(LLMCancelled):
        accumulate_stream(events(), cancel)
    assert len(seen) == 2


ERROR_TABLE = [
    (client_error("ThrottlingException", 429), LLMThrottled),
    (client_error("ServiceQuotaExceededException", 400), LLMThrottled),
    (client_error("ServiceUnavailableException", 503), LLMUnavailable),
    (client_error("InternalServerException", 500), LLMUnavailable),
    (client_error("ModelNotReadyException", 429), LLMUnavailable),
    (client_error("ModelErrorException", 424), LLMUnavailable),
    (client_error("SomethingNew", 502), LLMUnavailable),
    (client_error("ModelTimeoutException", 408), LLMTimeout),
    (ReadTimeoutError(endpoint_url="https://bedrock"), LLMTimeout),
    (ConnectTimeoutError(endpoint_url="https://bedrock"), LLMTimeout),
    (client_error("ValidationException", 400), LLMBadRequest),
    (client_error("ResourceNotFoundException", 404), LLMBadRequest),
    (client_error("AccessDeniedException", 403), LLMAuthError),
    (client_error("UnrecognizedClientException", 403), LLMAuthError),
    (client_error("ExpiredTokenException", 403), LLMAuthError),
    (NoCredentialsError(), LLMAuthError),
    (EndpointConnectionError(endpoint_url="https://bedrock"), LLMUnavailable),
    (ConnectionClosedError(endpoint_url="https://bedrock"), LLMUnavailable),
    (client_error("NewThrottle", 429), LLMThrottled),
    (client_error("NewAuth", 401), LLMAuthError),
    (client_error("NewForbidden", 403), LLMAuthError),
    (client_error("NewTeapot", 418), LLMBadRequest),
    (client_error("NoStatus", 0), LLMUnavailable),
    (
        EventStreamError({"Error": {"Code": "throttlingException", "Message": SECRET}}, "S"),
        LLMThrottled,
    ),
    (
        EventStreamError({"Error": {"Code": "validationException", "Message": SECRET}}, "S"),
        LLMBadRequest,
    ),
    (
        EventStreamError({"Error": {"Code": "internalServerException", "Message": SECRET}}, "S"),
        LLMUnavailable,
    ),
    (
        EventStreamError({"Error": {"Code": "modelTimeoutException", "Message": SECRET}}, "S"),
        LLMTimeout,
    ),
    (PartialCredentialsError(provider="env", cred_var=SECRET), LLMAuthError),
    (CredentialRetrievalError(provider="sso", error_msg=SECRET), LLMAuthError),
    (TokenRetrievalError(provider="sso", error_msg=SECRET), LLMAuthError),
    (NoRegionError(), LLMBadRequest),
    (BotoConnectionError(error=SECRET), LLMUnavailable),
    (HTTPClientError(error=SECRET), LLMUnavailable),
    (ResponseStreamingError(error=SECRET), LLMUnavailable),
    (ProxyConnectionError(proxy_url="http://p", error=SECRET), LLMUnavailable),
    (SSLError(endpoint_url="https://bedrock", error=SECRET), LLMUnavailable),
    (Urllib3ReadTimeout(None, "https://bedrock", SECRET), LLMTimeout),  # type: ignore[arg-type]
    (ProtocolError(SECRET), LLMUnavailable),
    (RuntimeError(SECRET), LLMUnavailable),
]


@pytest.mark.parametrize(("exc", "kind"), ERROR_TABLE, ids=lambda v: type(v).__name__)
def test_error_map_table(exc, kind):
    err = map_error(exc, model=MODEL)
    assert type(err) is kind
    assert err.provider == "bedrock" and err.model == MODEL


def test_error_detail_excludes_aws_message():
    for exc, _kind in ERROR_TABLE:
        err = map_error(exc, model=MODEL)
        assert SECRET not in err.detail and SECRET not in str(err) and SECRET not in repr(err)
    assert map_error(client_error("ThrottlingException", 429), model=MODEL).detail == (
        "ThrottlingException"
    )
    weird = map_error(client_error(f"Bad code {SECRET}", 400), model=MODEL)
    assert SECRET not in weird.detail


def test_map_error_returns_fresh_instances():
    exc = client_error("ThrottlingException", 429)
    assert map_error(exc, model=MODEL) is not map_error(exc, model=MODEL)


def test_kwargs_never_contain_blank_text_blocks():
    w = wire(
        system="  ",
        messages=(
            Message(role="user", content="hi"),
            Message(role="assistant", content=""),
            Message(role="user", content=" \n"),
        ),
    )
    kw = build_converse_kwargs(w)
    texts = [b["text"] for m in kw["messages"] for b in m["content"]]
    assert texts == ["hi", "(empty)", "(empty)"]
    assert "system" not in kw
