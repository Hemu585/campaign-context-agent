"""FastAPI entry point: one process, one worker, loopback only.

    .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.runner import AgentRunner
from app.config import Settings, get_settings
from app.db.client import GraphClient
from app.errors import AppError, install_error_handlers
from app.routes import campaigns, demo, memory, proposals, sessions, system
from app.security import LoopbackHostMiddleware
from app.services.decisions import DecisionService
from app.services.demo_edits import DemoEditService
from app.services.evaluation import EvaluationService
from app.services.mutations import MutationService
from app.services.proposals import ProposalService
from app.services.sessions import SessionService

API_VERSION = "0.1.0"
log = logging.getLogger("campaign_context")


def create_app(settings: Settings | None = None, *, model_factory: Callable[[], object] | None = None) -> FastAPI:
    """Build the app. ``model_factory`` exists only so automated tests can inject a labelled
    TEST DOUBLE; the default is the real local Ollama client."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            interrupted = await app.state.sessions.mark_interrupted_on_startup()
            if interrupted:
                log.warning("marked %d unfinished run(s) as interrupted after restart", interrupted)
        except AppError as exc:  # graph down or not seeded: the app still starts and reports it
            log.warning("startup recovery skipped: %s", exc.code)
        yield
        await app.state.graph.close()

    app = FastAPI(title="Campaign Context Agent", version=API_VERSION, lifespan=lifespan,
                  description="Local creator-replacement agent on FalkorDB and Ollama. Fictional demo data only.")
    graph = GraphClient(settings)
    mutations = MutationService(graph, settings)
    evaluation = EvaluationService(graph, settings)
    app.state.settings = settings
    app.state.nonce = secrets.token_urlsafe(32)  # new per backend process; the UI reads it from /api/bootstrap
    app.state.graph = graph
    app.state.mutations = mutations
    app.state.evaluation = evaluation
    app.state.sessions = SessionService(graph, mutations)
    app.state.decisions = DecisionService(graph, mutations)
    app.state.edits = DemoEditService(graph, mutations)
    app.state.proposals = ProposalService(graph, mutations, evaluation)
    app.state.runner = AgentRunner(settings=settings, client=graph, mutations=mutations,
                                   sessions=app.state.sessions, evaluation=evaluation,
                                   decisions=app.state.decisions, proposals=app.state.proposals,
                                   model_factory=model_factory)

    install_error_handlers(app)
    app.add_middleware(LoopbackHostMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origin_list,  # exact allowlist, never a wildcard
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "X-Local-Nonce", "Idempotency-Key"],
        allow_credentials=False,
        max_age=600,
    )
    for module in (system, campaigns, sessions, memory, proposals, demo):
        app.include_router(module.router)
    return app


app = create_app()
