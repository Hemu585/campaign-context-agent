"""Persistent sessions, agent runs (start, poll, cancel) and a run's evidence snapshot."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.errors import AppError
from app.models.responses import Run, RunEvidence, SessionDetail, SessionSummary
from app.routes.errors import ERROR_RESPONSES
from app.security import write_guard
from app.services.graph_reads import read_revision

router = APIRouter(prefix="/api", tags=["sessions", "runs"], responses=ERROR_RESPONSES)
SessionId = Path(pattern=r"^ses_[a-f0-9]{16}$")
RunId = Path(pattern=r"^run_[a-f0-9]{16}$")


class CreateSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="", max_length=80)


class StartRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campaign_id: str = Field(pattern=r"^[a-z0-9_]{1,64}$")
    message: str = Field(min_length=1, max_length=4000)


class EmptyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


async def _with_revision(request: Request, run: dict, *, active: bool | None = None) -> dict:
    try:
        current = await read_revision(request.app.state.graph)
    except AppError:
        current = None
    run["current_revision"] = current
    run["is_stale"] = current is not None and run.get("context_revision") != current
    run["active"] = active if active is not None else request.app.state.runner.active_run_id == run["id"]
    return run


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(request: Request, limit: int = Query(default=20, ge=1, le=100)):
    return await request.app.state.sessions.list_sessions(limit)


@router.post("/sessions", status_code=201, response_model=SessionDetail)
async def create_session(request: Request, body: CreateSession, key: uuid.UUID = Depends(write_guard)):
    return await request.app.state.sessions.create_session(body.title, str(key))


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(request: Request, session_id: str = SessionId):
    return await request.app.state.sessions.get_session(session_id)


@router.post("/sessions/{session_id}/runs", status_code=202, response_model=Run)
async def start_run(request: Request, body: StartRun, session_id: str = SessionId,
                    key: uuid.UUID = Depends(write_guard)):
    """Starts a real local-agent run in the background; poll GET /api/runs/{id}."""
    run = await request.app.state.runner.start(session_id=session_id, campaign_id=body.campaign_id,
                                               message=body.message, key=str(key))
    return await _with_revision(request, run)


@router.get("/runs/{run_id}", response_model=Run)
async def get_run(request: Request, run_id: str = RunId):
    # Ask the runner BEFORE reading the run: a run finishing in between then shows its terminal
    # status, so "queued/running but not active" can only mean no task is working on it any more.
    active = request.app.state.runner.active_run_id == run_id
    return await _with_revision(request, await request.app.state.sessions.get_run(run_id), active=active)


@router.post("/runs/{run_id}/cancel", response_model=Run)
async def cancel_run(request: Request, body: EmptyBody, run_id: str = RunId, _key: uuid.UUID = Depends(write_guard)):
    """Idempotent per run: cancelling a finished run returns it unchanged."""
    return await _with_revision(request, await request.app.state.runner.cancel(run_id))


@router.get("/runs/{run_id}/evidence", response_model=RunEvidence)
async def run_evidence(request: Request, run_id: str = RunId):
    run = await request.app.state.sessions.get_run(run_id)
    evaluation = run.get("evaluation")
    if not evaluation:
        raise AppError("EVIDENCE_NOT_AVAILABLE", "This run has no evaluation snapshot.", 404)
    return {"run_id": run_id, "campaign_id": evaluation["campaign_id"],
            "context_revision": evaluation["context_revision"], "as_of_ms": evaluation["as_of_ms"],
            "evidence_paths": evaluation["evidence_paths"], "sources": evaluation["sources"]}
