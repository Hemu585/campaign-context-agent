"""The single writer for receipt-backed and decision-affecting changes (ARCHITECTURE "Mutation integrity").

Order inside one application-wide asyncio lock (never held while waiting for the model):
1. Idempotency replay: same key and payload returns the original result; same key with
   a different operation or payload is IDEMPOTENCY_CONFLICT.
2. The caller's ``perform`` revalidates current graph state and runs ONE parameterized
   Cypher statement that re-checks the expected revision/state in MATCH/WHERE, applies
   every change and writes the MutationReceipt. No returned row means conflict.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.config import Settings
from app.db.client import GraphClient
from app.errors import AppError

WORKSPACE_ID = "ws_demo"


def payload_hash(operation: str, payload: dict) -> str:
    canonical = json.dumps({"operation": operation, "payload": payload}, sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Receipt:
    id: str
    operation: str
    payload_hash: str
    result_type: str
    result_id: str
    created_at_ms: int


@dataclass(frozen=True)
class MutationResult:
    result_type: str
    result_id: str
    replayed: bool
    revision: int | None = None


def stale(message: str = "The campaign information changed. Refresh and try again.", **details) -> AppError:
    return AppError("STALE_CONTEXT", message, 409, retryable=True, details=details)


Perform = Callable[[str], Awaitable[tuple[str, str, int | None]]]


class MutationService:
    def __init__(self, client: GraphClient, settings: Settings):
        self.client = client
        self.settings = settings
        self.lock = asyncio.Lock()

    async def receipt(self, key: str) -> Receipt | None:
        rows = await self.client.ro_query("Q08_receipt", {"key": key})
        return Receipt(**rows[0]) if rows else None

    async def run(self, operation: str, key: str, payload: dict, perform: Perform) -> MutationResult:
        digest = payload_hash(operation, payload)
        async with self.lock:
            existing = await self.receipt(key)
            if existing is not None:
                if existing.operation != operation or existing.payload_hash != digest:
                    raise AppError("IDEMPOTENCY_CONFLICT",
                                   "This request key was already used for a different request.", 409,
                                   details={"operation": existing.operation})
                return MutationResult(existing.result_type, existing.result_id, replayed=True)
            result_type, result_id, revision = await perform(digest)
            return MutationResult(result_type, result_id, replayed=False, revision=revision)
