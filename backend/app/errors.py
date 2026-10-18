"""Common error envelope (API_CONTRACTS "Errors").

Responses carry an actionable message without stack traces, filesystem paths or
model reasoning.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger("campaign_context")


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, *, retryable: bool = False,
                 details: dict | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable
        self.details = details or {}

    def body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "retryable": self.retryable,
                          "details": self.details}}


def graph_unavailable() -> AppError:
    return AppError("GRAPH_UNAVAILABLE",
                    "The FalkorDB graph is not reachable. Start it with `docker compose up -d` and retry.",
                    503, retryable=True)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(exc.body(), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"field": ".".join(str(p) for p in err.get("loc", []) if p != "body"), "problem": err.get("msg", "")}
            for err in exc.errors()
        ]
        err = AppError("INVALID_INPUT", "The request is not valid.", 422, details={"fields": fields[:10]})
        return JSONResponse(err.body(), status_code=422)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        err = AppError("INTERNAL_ERROR", "Something went wrong inside the local app. Check the backend log.", 500)
        return JSONResponse(err.body(), status_code=500)
