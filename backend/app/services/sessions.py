"""Persistent conversation sessions and runs (R16). None of these writes changes the
decision-context revision; creation is receipt-backed so retries never duplicate."""

from __future__ import annotations

import json
import uuid

from app.clock import business_now_ms, wall_now_ms
from app.db.client import GraphClient
from app.errors import AppError
from app.services.mutations import WORKSPACE_ID, MutationService

MAX_TITLE = 80
MAX_MESSAGE = 4000
RUN_JSON_FIELDS = ("trace_json", "evaluation_json", "final_json", "error_json")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def decode_run(row: dict) -> dict:
    run = dict(row["run"])
    run["session_id"] = row["session_id"]
    for name in RUN_JSON_FIELDS:
        raw = run.pop(name, None)
        run[name.removesuffix("_json")] = json.loads(raw) if raw else None
    return run


class SessionService:
    def __init__(self, client: GraphClient, mutations: MutationService):
        self.client = client
        self.mutations = mutations
        self.settings = mutations.settings

    async def create_session(self, title: str, key: str) -> dict:
        title = (title or "").strip()[:MAX_TITLE] or "New session"
        session_id = new_id("ses")

        async def perform(digest: str):
            rows = await self.client.query("Q08_create_session", {
                "workspace_id": WORKSPACE_ID, "key": key, "session_id": session_id, "title": title,
                "now_ms": wall_now_ms(), "payload_hash": digest})
            if not rows:
                raise AppError("STALE_CONTEXT", "The session could not be created; retry.", 409, retryable=True)
            return "session", rows[0]["id"], None

        result = await self.mutations.run("create_session", key, {"title": title}, perform)
        return await self.get_session(result.result_id)

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        return await self.client.ro_query("Q13_sessions", {"limit": max(1, min(limit, 100))})

    async def get_session(self, session_id: str) -> dict:
        rows = await self.client.ro_query("Q13_session", {"session_id": session_id})
        if not rows:
            raise AppError("SESSION_NOT_FOUND", f"Session {session_id!r} does not exist.", 404)
        s = rows[0]
        role_order = {"user": 0, "assistant": 1}
        s["messages"] = sorted(s["messages"], key=lambda m: (m["created_at_ms"], role_order.get(m["role"], 2), m["id"]))
        s["runs"] = sorted(s["runs"], key=lambda r: (r["created_at_ms"], r["id"]))
        return s

    async def create_run(self, session_id: str, campaign_id: str, message: str, key: str, *,
                         model: str, model_digest: str | None) -> dict:
        text = (message or "").strip()
        if not 1 <= len(text) <= MAX_MESSAGE:
            raise AppError("INVALID_INPUT", f"The message must be 1-{MAX_MESSAGE} characters.", 422)
        run_id, message_id = new_id("run"), new_id("msg")

        async def perform(digest: str):
            rows = await self.client.query("Q08_create_run", {
                "workspace_id": WORKSPACE_ID, "session_id": session_id, "campaign_id": campaign_id, "key": key,
                "message_id": message_id, "run_id": run_id, "text": text, "now_ms": wall_now_ms(),
                "as_of_ms": business_now_ms(self.settings), "model": model, "model_digest": model_digest,
                "payload_hash": digest})
            if not rows:
                await self.get_session(session_id)  # raises SESSION_NOT_FOUND when that is the reason
                raise AppError("CAMPAIGN_NOT_FOUND", f"Campaign {campaign_id!r} does not exist.", 404)
            return "run", rows[0]["id"], None

        result = await self.mutations.run(
            "create_run", key, {"session_id": session_id, "campaign_id": campaign_id, "message": text}, perform)
        return await self.get_run(result.result_id)

    async def get_run(self, run_id: str) -> dict:
        rows = await self.client.ro_query("Q13_run", {"run_id": run_id})
        if not rows:
            raise AppError("RUN_NOT_FOUND", f"Run {run_id!r} does not exist.", 404)
        return decode_run(rows[0])

    async def update_run(self, run_id: str, **props) -> None:
        """Run bookkeeping (status, phase, bounded JSON). Internal only; no receipt, no revision."""
        encoded = {}
        for name, value in props.items():
            if name in {f.removesuffix("_json") for f in RUN_JSON_FIELDS}:
                encoded[f"{name}_json"] = None if value is None else json.dumps(value, separators=(",", ":"))
            else:
                encoded[name] = value
        rows = await self.client.query("Q08_update_run", {"run_id": run_id, "props": encoded})
        if not rows:
            raise AppError("RUN_NOT_FOUND", f"Run {run_id!r} does not exist.", 404)

    async def mark_interrupted_on_startup(self) -> int:
        error = {"code": "RUN_INTERRUPTED",
                 "message": "The backend restarted before this run finished. Start a new run."}
        rows = await self.client.query("Q08_mark_interrupted", {"now_ms": wall_now_ms(),
                                                               "error_json": json.dumps(error)})
        return int(rows[0]["interrupted"]) if rows else 0
