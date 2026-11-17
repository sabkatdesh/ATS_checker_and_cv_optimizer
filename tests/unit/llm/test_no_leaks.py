import pytest
from pydantic import SecretStr

from app.adapters.llm.fake import Fail, Reply
from app.config.settings import AppSettings, ConfigError, load_settings
from app.observability.sentry import scrub_event
from app.ports.llm_errors import LLMThrottled, LLMUnavailable
from tests.unit.llm.leak_support import (
    SENTINEL,
    TEXT,
    assert_clean,
    build,
    request,
    run_captured,
)

GOOD = '{"answer": "a", "score": 1}'
ECHO = f"not json {TEXT}"  # a model that echoes the prompt back as invalid output


def _unavailable(n: int = 4):
    return [Fail(LLMUnavailable)] * n


SCENARIOS = {
    "success": ({"p1": [Reply(GOOD)]}, False),
    "one_repair": ({"p1": [Reply("nope"), Reply(GOOD)]}, False),
    "throttle_then_success": ({"p1": [Fail(LLMThrottled), Reply(GOOD)]}, False),
    "refusal": ({"p1": [Reply("", stop="refused")]}, False),
    "invalid_output_echoing_prompt": ({"p1": [Reply(ECHO), Reply(ECHO)]}, False),
    "fallback_also_fails": ({"p1": _unavailable()}, True),
}


@pytest.mark.parametrize("name", SCENARIOS)
def test_router_logs_and_records_have_no_content(name):
    script, fallback = SCENARIOS[name]
    router, sink = build(script, fallback=fallback)
    logged, raised = run_captured(router, request())
    records = "".join(r.model_dump_json() for r in sink.records)
    assert sink.records, "every call must leave a usage record"
    assert '"llm.call"' in logged
    assert_clean(logged, raised, records)


def test_router_unstructured_success_has_no_content():
    router, sink = build({"p1": [Reply(f"echo {TEXT}")]})
    logged, raised = run_captured(router, request(schema=None))
    assert_clean(logged, raised, "".join(r.model_dump_json() for r in sink.records))


def test_leak_check_can_fail():
    # Guards the guard: a deliberately leaky blob must trip assert_clean.
    with pytest.raises(AssertionError):
        assert_clean(f"event with {SENTINEL}")


def test_settings_repr_hides_provider_keys(monkeypatch):
    values = {
        "LLM__OPENAI_API_KEY": "sk-test-SECRET-openai",
        "LLM__ANTHROPIC_API_KEY": "sk-ant-SECRET-anthropic",
        "LLM__GEMINI_API_KEY": "gem-SECRET-gemini",
        "AZURE_OPENAI_KEY": "az-SECRET-azure",
    }
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    settings = AppSettings(_env_file=None)
    assert settings.llm.openai_api_key == SecretStr("sk-test-SECRET-openai")  # really loaded
    blobs = [repr(settings), str(settings), settings.model_dump_json(), repr(settings.llm)]
    monkeypatch.setenv("API__CORS_ORIGINS", "[not-json")
    monkeypatch.setenv("ENV", "bogus")
    with pytest.raises(ConfigError) as err:
        load_settings(_env_file=None)
    blobs += [str(err.value), repr(err.value)]
    for blob in blobs:
        assert "SECRET" not in blob


def test_sentry_before_send_drops_llm_exception_vars():
    frame_vars = {"req": f"LLMRequest(messages=[{TEXT}])", "wire": TEXT, "api_key": "sk-SECRET"}
    event = {
        "exception": {
            "values": [
                {
                    "type": "LLMBadRequest",
                    "value": f"bad request for {TEXT}",
                    "stacktrace": {"frames": [{"function": "complete", "vars": frame_vars}]},
                }
            ]
        },
        "breadcrumbs": {"values": [{"message": "llm.call", "data": {"messages": [TEXT]}}]},
        "extra": {"prompt": TEXT, "system": TEXT, "api_key": "sk-SECRET", "x-api-key": "sk-SECRET"},
    }
    out = scrub_event(event, {})
    blob = str(out)
    assert_clean(blob)
    assert "sk-SECRET" not in blob
    assert "vars" not in out["exception"]["values"][0]["stacktrace"]["frames"][0]
