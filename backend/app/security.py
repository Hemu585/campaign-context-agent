"""Local-browser write boundary (API_CONTRACTS "Mutation headers", SECURITY_PRIVACY).

- Every request must carry a loopback Host header (blocks DNS-rebinding style access).
- Every POST/PATCH needs JSON, the per-process nonce from /api/bootstrap, an
  allowlisted Origin when a browser sends one, and a UUID Idempotency-Key.
This is a local write boundary for one trusted operator, not multi-user authentication.
"""

from __future__ import annotations

import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.errors import AppError

LOOPBACK_HOSTNAMES = {"127.0.0.1", "localhost", "[::1]"}


def _hostname(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith("["):
        return host.split("]")[0] + "]"
    return host.split(":")[0]


class LoopbackHostMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if _hostname(request.headers.get("host", "")) not in LOOPBACK_HOSTNAMES:
            err = AppError("LOCAL_ACCESS_REQUIRED", "This local app only answers on 127.0.0.1.", 403)
            return JSONResponse(err.body(), status_code=403)
        return await call_next(request)


async def write_guard(request: Request) -> uuid.UUID:
    """Dependency for every state-changing route. Returns the validated Idempotency-Key."""
    settings = request.app.state.settings
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.allowed_origin_list:
        raise AppError("LOCAL_ACCESS_REQUIRED", "Writes are only accepted from the local app.", 403)
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("application/json"):
        raise AppError("INVALID_INPUT", "Send the request body as application/json.", 415)
    if request.headers.get("x-local-nonce") != request.app.state.nonce:
        raise AppError("INVALID_NONCE", "The local session nonce is missing or out of date. Reload the app.", 403)
    raw_key = request.headers.get("idempotency-key", "")
    try:
        return uuid.UUID(raw_key)
    except ValueError:
        raise AppError("INVALID_INPUT", "An Idempotency-Key UUID header is required.", 400) from None
