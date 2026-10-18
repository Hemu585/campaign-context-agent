"""Background runs over HTTP with a labelled TEST DOUBLE model and real FalkorDB (R16, R17; T08, T16 part).

The real local model is exercised separately by `python -m app.cli verify-model`.
"""

import asyncio
import uuid

import httpx
import pytest
from helpers.fake_model import HAPPY_PATH, ScriptedModel
from helpers.graphq import scalar

from app.config import Settings
from app.errors import AppError
from app.main import create_app

BASE = "http://127.0.0.1:8000"
ORIGIN = "http://127.0.0.1:5173"


def make_api(settings, factory):
    app = create_app(settings, model_factory=factory)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE, headers={"Origin": ORIGIN})
    return app, client


async def write_headers(client, key=None):
    nonce = (await client.get("/api/bootstrap")).json()["nonce"]
    return {"Content-Type": "application/json", "X-Local-Nonce": nonce, "Idempotency-Key": key or str(uuid.uuid4())}


async def new_session(client):
    res = await client.post("/api/sessions", json={"title": "Run test"}, headers=await write_headers(client))
    return res.json()["id"]


async def wait_done(client, run_id, timeout=20):
    for _ in range(int(timeout / 0.05)):
        run = (await client.get(f"/api/runs/{run_id}")).json()
        if run["status"] not in ("queued", "running"):
            return run
        await asyncio.sleep(0.05)
    raise AssertionError("run did not finish")


@pytest.fixture
async def harness(seeded, test_settings):
    created = []

    def build(factory):
        app, client = make_api(test_settings, factory)
        created.append((app, client))
        return app, client

    yield build
    for app, client in created:
        await client.aclose()
        await app.state.graph.close()


async def test_run_completes_persists_and_links_considered_creators(harness, seeded):
    app, client = harness(lambda: ScriptedModel(list(HAPPY_PATH)))
    sid = await new_session(client)
    res = await client.post(f"/api/sessions/{sid}/runs", headers=await write_headers(client),
                            json={"campaign_id": "camp_01", "message": "Find a replacement and explain conflicts."})
    assert res.status_code == 202 and res.json()["status"] == "queued"
    run = await wait_done(client, res.json()["id"])
    assert run["status"] == "completed" and run["phase"] == "done" and run["is_stale"] is False
    assert run["final"]["recommended_creator_ids"] == ["cr_02", "cr_04", "cr_09"]
    assert run["proposal_id"] and run["evaluation"]["context_revision"] == 1
    assert [t["tool"] for t in run["trace"] if t["type"] == "tool"][-1] == "stage_replacement_proposal"
    session = (await client.get(f"/api/sessions/{sid}")).json()
    assert [m["role"] for m in session["messages"]] == ["user", "assistant"]
    assert "Mira Vale" in session["messages"][1]["text"]
    assert await scalar(seeded, "MATCH (:Run {id: $id})-[:CONSIDERED]->(c) RETURN count(c)", {"id": run["id"]}) == 12
    assert await scalar(seeded, "MATCH (:Run {id: $id})-[:USED_SOURCE]->(s) RETURN count(s)", {"id": run["id"]}) > 10
    evidence = (await client.get(f"/api/runs/{run['id']}/evidence")).json()
    assert any(p["id"] == "cr_03:exclusivity:agr_cr03" for p in evidence["evidence_paths"])
    proposal = (await client.get(f"/api/proposals/{run['proposal_id']}")).json()
    assert proposal["approvable"] is True
    approved = await client.post(f"/api/proposals/{run['proposal_id']}/approve", headers=await write_headers(client),
                                 json={"expected_revision": 1})
    assert approved.status_code == 200


async def test_only_one_run_at_a_time(harness):
    gate = asyncio.Event()
    app, client = harness(lambda: ScriptedModel(list(HAPPY_PATH), block=gate))
    sid = await new_session(client)
    first = await client.post(f"/api/sessions/{sid}/runs", headers=await write_headers(client),
                              json={"campaign_id": "camp_01", "message": "Find a replacement"})
    second = await client.post(f"/api/sessions/{sid}/runs", headers=await write_headers(client),
                               json={"campaign_id": "camp_01", "message": "Find another"})
    assert second.status_code == 409 and second.json()["error"]["code"] == "RUN_BUSY"
    gate.set()
    assert (await wait_done(client, first.json()["id"]))["status"] == "completed"


async def test_retrying_the_same_request_does_not_start_a_second_run(harness, seeded):
    gate = asyncio.Event()
    app, client = harness(lambda: ScriptedModel(list(HAPPY_PATH), block=gate))
    sid = await new_session(client)
    key = str(uuid.uuid4())
    body = {"campaign_id": "camp_01", "message": "Find a replacement"}
    a = await client.post(f"/api/sessions/{sid}/runs", headers=await write_headers(client, key), json=body)
    b = await client.post(f"/api/sessions/{sid}/runs", headers=await write_headers(client, key), json=body)
    assert a.json()["id"] == b.json()["id"]
    gate.set()
    await wait_done(client, a.json()["id"])
    assert await scalar(seeded, "MATCH (r:Run) RETURN count(r)") == 1


async def test_cancel_stops_tools_and_creates_no_draft(harness, seeded):
    gate = asyncio.Event()
    app, client = harness(lambda: ScriptedModel(list(HAPPY_PATH), block=gate))
    sid = await new_session(client)
    run = (await client.post(f"/api/sessions/{sid}/runs", headers=await write_headers(client),
                             json={"campaign_id": "camp_01", "message": "Find a replacement"})).json()
    await asyncio.sleep(0.1)
    cancelled = await client.post(f"/api/runs/{run['id']}/cancel", headers=await write_headers(client), json={})
    assert cancelled.json()["status"] == "cancelled"
    gate.set()
    await asyncio.sleep(0.2)
    final = (await client.get(f"/api/runs/{run['id']}")).json()
    assert final["status"] == "cancelled" and final["error"]["code"] == "CANCELLED"
    assert await scalar(seeded, "MATCH (p:Proposal) RETURN count(p)") == 0
    again = await client.post(f"/api/runs/{run['id']}/cancel", headers=await write_headers(client), json={})
    assert again.json()["status"] == "cancelled"  # idempotent per run
    messages = (await client.get(f"/api/sessions/{sid}")).json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"] and "cancelled" in messages[1]["text"]


async def test_failed_run_is_visible_and_its_draft_is_unusable(harness, seeded):
    script = list(HAPPY_PATH[:5]) + [HAPPY_PATH[5].__class__(content='{"outcome": "nonsense"}')] * 2
    app, client = harness(lambda: ScriptedModel(script))
    sid = await new_session(client)
    run = (await client.post(f"/api/sessions/{sid}/runs", headers=await write_headers(client),
                             json={"campaign_id": "camp_01", "message": "Find a replacement"})).json()
    done = await wait_done(client, run["id"])
    assert done["status"] == "failed" and done["error"]["code"] == "INVALID_MODEL_OUTPUT"
    proposal = (await client.get("/api/proposals")).json()[0]
    assert proposal["approvable"] is False and proposal["unusable_reason"] == "run_not_completed"


async def test_a_failed_run_is_recorded_even_when_the_full_record_cannot_be_written(harness, seeded):
    # Seen in T18 on the 5.9 GB machine: Ollama ran out of memory mid-run, and recording that
    # failure then raised MemoryError, which left the run "running" with no task behind it.
    app, client = harness(lambda: ScriptedModel([AppError("MODEL_UNAVAILABLE", "TEST DOUBLE: model stopped", 503)]))
    graph = app.state.graph
    real_query = graph.query
    refused: list[str] = []

    async def query_failing_once(query_id, params=None):
        if query_id == "Q08_end_run" and "trace_json" in params["props"] and not refused:
            refused.append(query_id)
            raise MemoryError
        return await real_query(query_id, params)

    graph.query = query_failing_once
    sid = await new_session(client)
    body = {"campaign_id": "camp_01", "message": "Find a replacement"}
    run = (await client.post(f"/api/sessions/{sid}/runs", headers=await write_headers(client), json=body)).json()
    done = await wait_done(client, run["id"])
    assert refused == ["Q08_end_run"]
    assert done["status"] == "failed" and done["error"]["code"] == "MODEL_UNAVAILABLE" and done["active"] is False
    # The runner is free again: the next request starts a run instead of RUN_BUSY.
    again = await client.post(f"/api/sessions/{sid}/runs", headers=await write_headers(client), json=body)
    assert again.status_code == 202
    await wait_done(client, again.json()["id"])


async def test_a_retried_start_runs_a_run_whose_first_attempt_failed_before_scheduling(harness, seeded):
    # Review fix C3: the run and its receipt were written, then reading it back failed, so the
    # first request errored before the task was scheduled. The retry (same key) must run it.
    app, client = harness(lambda: ScriptedModel(HAPPY_PATH))
    sessions = app.state.sessions
    real_get_run = sessions.get_run
    failed: list[str] = []

    async def get_run_failing_once(run_id):
        if not failed:
            failed.append(run_id)
            raise AppError("GRAPH_UNAVAILABLE", "TEST: transient read failure", 503, retryable=True)
        return await real_get_run(run_id)

    sessions.get_run = get_run_failing_once
    sid = await new_session(client)
    headers = await write_headers(client)
    body = {"campaign_id": "camp_01", "message": "Find a replacement"}
    first = await client.post(f"/api/sessions/{sid}/runs", headers=headers, json=body)
    assert first.status_code == 503 and failed
    again = await client.post(f"/api/sessions/{sid}/runs", headers=headers, json=body)
    assert again.status_code == 202 and again.json()["id"] == failed[0]
    done = await wait_done(client, failed[0])
    assert done["status"] == "completed"
    assert await scalar(seeded, "MATCH (r:Run) RETURN count(r)") == 1


async def test_missing_local_model_creates_no_run(seeded):
    settings = Settings(_env_file=None, falkordb_graph=seeded.graph_name, ollama_model="qwen3:not-installed")
    app, client = make_api(settings, None)
    try:
        sid = await new_session(client)
        res = await client.post(f"/api/sessions/{sid}/runs", headers=await write_headers(client),
                                json={"campaign_id": "camp_01", "message": "Find a replacement"})
        assert res.status_code == 503 and res.json()["error"]["code"] in {"MODEL_NOT_INSTALLED", "MODEL_UNAVAILABLE"}
        assert await scalar(seeded, "MATCH (r:Run) RETURN count(r)") == 0
    finally:
        await client.aclose()
        await app.state.graph.close()
