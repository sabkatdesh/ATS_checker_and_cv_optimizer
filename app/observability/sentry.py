"""Optional Sentry: off without a DSN; events are scrubbed of bodies, headers and messages."""

from typing import Any

import sentry_sdk

from app.config.settings import AppSettings
from app.observability.redaction import REDACTED, redact_value

_DROPPED_HEADERS = {"authorization", "cookie"}


def scrub_event(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "cookies", "query_string"):
            request.pop(key, None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                k: v for k, v in headers.items() if k.lower() not in _DROPPED_HEADERS
            }
    for exc in (event.get("exception") or {}).get("values", []):
        exc["value"] = REDACTED
    if "breadcrumbs" in event:
        event["breadcrumbs"] = redact_value("breadcrumbs", event["breadcrumbs"])
    if "extra" in event:
        event["extra"] = redact_value("extra", event["extra"])
    return event


def init_sentry(settings: AppSettings) -> bool:
    if settings.sentry_dsn is None:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.env,
        release=settings.obs.release,
        send_default_pii=False,
        max_request_body_size="never",
        traces_sample_rate=0.0,
        before_send=scrub_event,  # type: ignore[arg-type]
    )
    return True
