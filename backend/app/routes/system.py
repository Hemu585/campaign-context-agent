"""GET /api/health and GET /api/bootstrap."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.agent.ollama import probe_model
from app.clock import business_now_ms, clock_label
from app.db.seed import workspace_state
from app.errors import AppError
from app.models.responses import Bootstrap, Health

router = APIRouter(prefix="/api", tags=["system"])


async def _graph_info(request: Request) -> dict:
    st = request.app.state
    info = {"reachable": False, "graph": st.settings.falkordb_graph, "seeded": False, "seed_status": None,
            "dataset_version": None, "revision": None}
    if not await st.graph.ping():
        return info
    info["reachable"] = True
    try:
        state = await workspace_state(st.graph)
    except AppError:
        state = None
    if state:
        info.update(seeded=state["seed_status"] == "complete", seed_status=state["seed_status"],
                    dataset_version=state["dataset_version"], revision=state["revision"])
    return info


@router.get("/health", response_model=Health, responses={503: {"model": Health, "description": "Degraded"}})
async def health(request: Request) -> JSONResponse:
    st = request.app.state
    graph = await _graph_info(request)
    model = await probe_model(st.settings)
    healthy = graph["reachable"] and graph["seeded"] and model.installed
    body = {
        "status": "ok" if healthy else "degraded",
        "backend": {"version": request.app.version, "demo_mode": st.settings.demo_mode,
                    "clock": clock_label(st.settings), "as_of_ms": business_now_ms(st.settings)},
        "graph": graph,
        "model": asdict(model),
        "synthetic_data": True,
    }
    return JSONResponse(body, status_code=200 if healthy else 503)


@router.get("/bootstrap", response_model=Bootstrap)
async def bootstrap(request: Request) -> dict:
    st = request.app.state
    graph = await _graph_info(request)
    return {
        "nonce": st.nonce,
        "workspace_id": "ws_demo" if graph["seeded"] else None,
        "context_revision": graph["revision"],
        "synthetic_data": True,
        "demo_mode": st.settings.demo_mode,
        "as_of_ms": business_now_ms(st.settings),
        "clock": clock_label(st.settings),
        "model": st.settings.ollama_model,
    }
