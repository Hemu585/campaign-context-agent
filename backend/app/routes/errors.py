"""Shared OpenAPI declarations for the error envelope, so the frontend gets typed errors."""

from app.models.responses import ErrorEnvelope

ERROR_RESPONSES = {
    code: {"model": ErrorEnvelope, "description": text}
    for code, text in [(400, "Invalid request"), (403, "Local write boundary refused the request"),
                       (404, "Not found"), (409, "Conflict (stale, busy, filled, idempotency)"),
                       (415, "Unsupported content type"), (422, "Validation error"),
                       (503, "Graph or local model unavailable")]
}
