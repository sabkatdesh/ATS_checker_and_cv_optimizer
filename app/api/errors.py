from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self, code: str, status: int, title: str, detail: str | None = None, **extras: Any
    ) -> None:
        super().__init__(detail or title)
        self.code = code
        self.status = status
        self.title = title
        self.detail = detail
        self.extras = extras


async def _handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)  # noqa: S101
    body = {
        "type": f"/problems/{exc.code.lower().replace('_', '-')}",
        "title": exc.title,
        "status": exc.status,
        "code": exc.code,
        "detail": exc.detail,
        "request_id": getattr(request.state, "request_id", None),
        **exc.extras,
    }
    return JSONResponse(body, status_code=exc.status, media_type="application/problem+json")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
