from typing import Any

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.adapters.db.errors import DbConflict, DbUnavailable


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


async def _handle_db_unavailable(request: Request, exc: Exception) -> JSONResponse:
    return await _handle_app_error(
        request,
        AppError("DB_UNAVAILABLE", 503, "Service unavailable", "Please try again shortly."),
    )


async def _handle_db_conflict(request: Request, exc: Exception) -> JSONResponse:
    return await _handle_app_error(
        request, AppError("DB_CONFLICT", 409, "Conflict", "Please retry the request.")
    )


async def _handle_psycopg(request: Request, exc: Exception) -> JSONResponse:
    return await _handle_db_unavailable(request, exc)


async def _handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
    return await _handle_app_error(
        request, AppError("INTERNAL_ERROR", 500, "Internal error", "Something went wrong.")
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(DbUnavailable, _handle_db_unavailable)
    app.add_exception_handler(DbConflict, _handle_db_conflict)
    app.add_exception_handler(psycopg.Error, _handle_psycopg)
    app.add_exception_handler(Exception, _handle_unhandled)
