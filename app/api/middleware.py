"""Pure-ASGI request-id + access-log middleware."""

import re
import time
import uuid
from typing import Any

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = structlog.get_logger("http")


class RequestIdMiddleware:
    HEADER = "x-request-id"
    VALID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        inbound = dict(scope.get("headers") or []).get(self.HEADER.encode(), b"").decode("latin-1")
        rid = inbound if self.VALID.match(inbound) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = rid
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)
        status: dict[str, Any] = {"code": 500}
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", rid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            log.error("http.request", **self._fields(scope, 500, start), exc_info=True)
            raise
        else:
            log.info("http.request", **self._fields(scope, status["code"], start))
        finally:
            structlog.contextvars.clear_contextvars()

    @staticmethod
    def _fields(scope: Scope, code: int, start: float) -> dict[str, Any]:
        return {
            "method": scope["method"],
            "path": scope["path"],
            "status": code,
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        }
