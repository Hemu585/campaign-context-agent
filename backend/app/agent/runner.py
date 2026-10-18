"""Background agent runs: one active run, persisted progress, cancellation (ARCHITECTURE "Runtime
boundaries", AGENT_WORKFLOW "Limits and recovery").

A run is created (receipt-backed) only after the graph and the local model are confirmed, then
executed as an in-process asyncio task while the UI polls GET /api/runs/{id}. Phases come from
real tool events. Cancelling marks the run cancelled in the graph FIRST (so no draft can be
staged afterwards: staging requires a running run) and then cancels the task, which aborts the
in-flight model request. Failed, cancelled and interrupted runs keep their trace but can never
be approved.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable

from app.agent.loop import AgentLimits, run_agent
from app.agent.ollama import OllamaChat, probe_model
from app.agent.tools import AgentServices, RunContext
from app.clock import wall_now_ms
from app.config import Settings
from app.db.client import GraphClient
from app.errors import AppError, graph_unavailable
from app.services.campaigns import list_campaigns
from app.services.decisions import DecisionService
from app.services.evaluation import EvaluationService
from app.services.mutations import MutationService
from app.services.proposals import ProposalService
from app.services.sessions import SessionService, new_id

log = logging.getLogger("campaign_context.runner")
TERMINAL = {"completed", "needs_clarification", "failed", "cancelled", "interrupted"}
HISTORY_MESSAGES = 4
TRACE_LIMIT = 60


class AgentRunner:
    def __init__(self, *, settings: Settings, client: GraphClient, mutations: MutationService,
                 sessions: SessionService, evaluation: EvaluationService, decisions: DecisionService,
                 proposals: ProposalService, model_factory: Callable[[], object] | None = None):
        self.settings = settings
        self.client = client
        self.mutations = mutations
        self.sessions = sessions
        self.services = AgentServices(client, evaluation, decisions, proposals)
        self.model_factory = model_factory or (lambda: OllamaChat(settings))
        self._start_lock = asyncio.Lock()
        self._cancelled: set[str] = set()
        self.active_run_id: str | None = None
        self.task: asyncio.Task | None = None

    def limits(self) -> AgentLimits:
        return AgentLimits(max_turns=self.settings.agent_max_turns, max_tool_calls=self.settings.agent_max_tool_calls,
                           timeout_s=float(self.settings.agent_run_timeout_seconds))

    async def start(self, *, session_id: str, campaign_id: str, message: str, key: str) -> dict:
        async with self._start_lock:
            if await self.mutations.receipt(key) is not None:  # client retry: replay, never start twice
                run = await self.sessions.create_run(session_id, campaign_id, message, key,
                                                     model=self.settings.ollama_model, model_digest=None)
                if run["status"] != "queued" or self.active_run_id == run["id"]:
                    return run
                # The first attempt wrote this run but failed before scheduling it (for example the
                # read-back failed). Start it now, or record why it cannot start: never leave it queued.
                if self.active_run_id is not None:
                    await self._end_safely(run["id"], "failed", {
                        "code": "RUN_BUSY", "message": "Another run started before this one could begin."}, None, None)
                    return await self.sessions.get_run(run["id"])
                try:
                    model, _ = await self._ready_model()
                except AppError as exc:
                    await self._end_safely(run["id"], "failed", {"code": exc.code, "message": exc.message}, None, None)
                    raise
                return self._launch(run, model, message)
            if self.active_run_id is not None:
                raise AppError("RUN_BUSY", "Another run is in progress. Wait for it to finish or cancel it.", 409,
                               details={"active_run_id": self.active_run_id})
            model, digest = await self._ready_model()
            run = await self.sessions.create_run(session_id, campaign_id, message, key,
                                                 model=self.settings.ollama_model, model_digest=digest)
            return self._launch(run, model, message)

    async def _ready_model(self) -> tuple[object, str | None]:
        """The graph must answer and the local model must be installed before a run is scheduled."""
        if not await self.client.ping():
            raise graph_unavailable()
        model = self.model_factory()
        if getattr(model, "is_test_double", False):
            return model, None
        status = await probe_model(self.settings)
        if not status.reachable:
            raise AppError("MODEL_UNAVAILABLE", status.detail, 503, retryable=True)
        if not status.installed:
            raise AppError("MODEL_NOT_INSTALLED", status.detail, 503)
        return model, status.digest

    def _launch(self, run: dict, model, message: str) -> dict:
        self.active_run_id = run["id"]
        self.task = asyncio.create_task(self._execute(run, model, message), name=f"agent-run-{run['id']}")
        return run

    async def cancel(self, run_id: str) -> dict:
        run = await self.sessions.get_run(run_id)
        if run["status"] in TERMINAL:
            return run
        self._cancelled.add(run_id)  # the task stops at its next event, even before task.cancel() lands
        await self._end(run_id, "cancelled", {"code": "CANCELLED", "message": "The operator cancelled this run."},
                        None, None)
        if self.active_run_id == run_id and self.task is not None:
            task = self.task
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        return await self.sessions.get_run(run_id)

    async def wait_idle(self, timeout: float = 30) -> None:
        if self.task is not None:
            await asyncio.wait_for(asyncio.shield(self.task), timeout=timeout)

    async def _history(self, session_id: str, run_id: str) -> list[dict]:
        session = await self.sessions.get_session(session_id)
        prior = [m for m in session["messages"] if m["run_id"] != run_id]
        return [{"role": m["role"], "content": (m["text"] or "")[:400]} for m in prior[-HISTORY_MESSAGES:]]

    async def _execute(self, run: dict, model, message: str) -> None:
        run_id = run["id"]
        trace: list[dict] = []
        ctx = RunContext(run_id=run_id, session_id=run["session_id"], campaign_id=run["campaign_id"],
                         revision=run["context_revision"], as_of_ms=run["as_of_ms"])

        async def emit(event: dict) -> None:
            if run_id in self._cancelled:
                raise asyncio.CancelledError
            event["seq"] = len(trace) + 1
            trace.append(event)
            fields = {"trace": trace[-TRACE_LIMIT:]}
            if event.get("phase"):
                fields["phase"] = event["phase"]
            await self.sessions.update_run(run_id, **fields)

        try:
            await self.sessions.update_run(run_id, status="running", phase="reading_campaign",
                                           started_at_ms=wall_now_ms())
            title = next((c.title for c in await list_campaigns(self.client) if c.id == run["campaign_id"]),
                         run["campaign_id"])
            result = await run_agent(model=model, ctx=ctx, services=self.services, message=message,
                                     history=await self._history(run["session_id"], run_id), campaign_title=title,
                                     limits=self.limits(), emit=emit)
            await self._finalize(run_id, ctx, result, trace)
        except asyncio.CancelledError:
            await self._end_safely(run_id, "cancelled",
                                   {"code": "CANCELLED", "message": "The operator cancelled this run."}, trace, ctx)
        except AppError as exc:
            await self._end_safely(run_id, "failed", {"code": exc.code, "message": exc.message, "details": exc.details},
                                   trace, ctx)
        except Exception:  # noqa: BLE001 - recorded as a visible failure, never as success
            log.exception("agent run %s crashed", run_id)
            await self._end_safely(run_id, "failed",
                                   {"code": "INTERNAL_ERROR", "message": "The run stopped unexpectedly."}, trace, ctx)
        finally:
            if self.active_run_id == run_id:
                self.active_run_id = None
                self.task = None

    async def _finalize(self, run_id: str, ctx: RunContext, result: dict, trace: list[dict]) -> None:
        evaluation = ctx.evaluation
        considered, sources = [], []
        if evaluation is not None:
            considered = [{"creator_id": c.creator_id, "status": c.status,
                           "reason_codes": [ch.reason_code for ch in c.checks
                                            if ch.result in ("fail", "unknown") and ch.reason_code]}
                          for c in evaluation.candidates]
            sources = sorted({s.id for s in evaluation.sources})
        props = {
            "status": result["status"], "phase": "done", "finished_at_ms": wall_now_ms(),
            "proposal_id": result["proposal_id"],
            "trace_json": json.dumps(trace[-TRACE_LIMIT:], separators=(",", ":")),
            "final_json": json.dumps(result, separators=(",", ":"), ensure_ascii=False),
            "evaluation_json": (json.dumps(evaluation.model_dump(mode="json", by_alias=True), separators=(",", ":"),
                                           ensure_ascii=False) if evaluation is not None else None),
            "tool_calls": ctx.tool_calls,
        }
        await self.client.query("Q08_finalize_run", {
            "run_id": run_id, "props": props, "message_id": new_id("msg"), "text": result["summary"],
            "now_ms": wall_now_ms(), "source_ids": sources, "considered": considered})

    async def _end_safely(self, run_id: str, status: str, error: dict, trace: list[dict] | None,
                          ctx: RunContext | None) -> None:
        """Always try to leave the run in a terminal state. If the full record cannot be written
        (MemoryError on this 5.9 GB machine, or the graph dropped), retry once with only the status
        and error. If that fails too, the next backend start marks the run interrupted."""
        try:
            await self._end(run_id, status, error, trace, ctx)
        except Exception:  # noqa: BLE001 - includes MemoryError
            log.exception("could not record the end of run %s; retrying with a minimal record", run_id)
            try:
                await self._end(run_id, status, {"code": error["code"], "message": str(error["message"])[:300]},
                                None, None)
            except Exception:  # noqa: BLE001
                log.exception("run %s is left unfinished in the graph until the next backend start", run_id)

    async def _end(self, run_id: str, status: str, error: dict, trace: list[dict] | None,
                   ctx: RunContext | None) -> None:
        props = {"status": status, "phase": status, "finished_at_ms": wall_now_ms(),
                 "error_json": json.dumps(error, separators=(",", ":"), default=str)}
        if trace is not None:
            props["trace_json"] = json.dumps(trace[-TRACE_LIMIT:], separators=(",", ":"))
        if ctx is not None and ctx.evaluation is not None:
            props["evaluation_json"] = json.dumps(ctx.evaluation.model_dump(mode="json", by_alias=True),
                                                  separators=(",", ":"), ensure_ascii=False)
        verb = "was cancelled" if status == "cancelled" else "failed"
        text = f"This run {verb}: {error['message']} ({error['code']}). Nothing was approved."
        await self.client.query("Q08_end_run", {"run_id": run_id, "props": props, "message_id": new_id("msg"),
                                                "text": text, "now_ms": wall_now_ms()})
